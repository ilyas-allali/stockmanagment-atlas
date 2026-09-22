#!/usr/bin/env python3
"""Atlas: a local stock and sales workspace. Python 3.10+, no dependencies."""
import argparse
import csv
import io
import json
import mimetypes
import re
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ValidationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def label(value, name, required=True, limit=160):
    require(isinstance(value, str), f"{name} : texte attendu.")
    value = value.strip()
    require(not required or bool(value), f"{name} est obligatoire.")
    require(len(value) <= limit, f"{name} : maximum {limit} caractères.")
    return value


def integer(value, name, minimum=0, maximum=1_000_000):
    require(not isinstance(value, bool), f"{name} invalide.")
    try:
        number = Decimal(str(value))
        require(number.is_finite() and number == number.to_integral_value(), f"{name} doit être un entier.")
        require(minimum <= number <= maximum, f"{name} doit être entre {minimum} et {maximum}.")
        return int(number)
    except InvalidOperation:
        raise ValidationError(f"{name} invalide.")


def money(value, name="Montant"):
    try:
        number = Decimal(str(value).replace(',', '.'))
        require(number.is_finite() and 0 <= number <= 10_000_000, f"{name} invalide.")
        require(number * 100 == (number * 100).to_integral_value(), f"{name} : maximum deux décimales.")
        return int(number * 100)
    except InvalidOperation:
        raise ValidationError(f"{name} invalide.")


def now():
    return datetime.now().isoformat(timespec='seconds')


class Store:
    def __init__(self, path, demo=True):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, address TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', demo INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, sku TEXT NOT NULL COLLATE NOCASE UNIQUE, name TEXT NOT NULL, category TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>=0), price INTEGER NOT NULL CHECK(price>=0), stock INTEGER NOT NULL CHECK(stock>=0), minimum INTEGER NOT NULL CHECK(minimum>=0));
                CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, customer_id INTEGER REFERENCES customers(id), customer_name TEXT NOT NULL, created_at TEXT NOT NULL, subtotal INTEGER NOT NULL, tax_bps INTEGER NOT NULL, tax INTEGER NOT NULL, total INTEGER NOT NULL, paid INTEGER NOT NULL CHECK(paid>=0 AND paid<=total), status TEXT NOT NULL DEFAULT 'active', note TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS sale_items (id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), price INTEGER NOT NULL, cost INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS movements (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), kind TEXT NOT NULL, quantity INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL, sale_id INTEGER REFERENCES sales(id));
                CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), amount INTEGER NOT NULL, created_at TEXT NOT NULL, method TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operation_requests (request_key TEXT PRIMARY KEY, action TEXT NOT NULL, result TEXT NOT NULL);
            ''')
            fresh = db.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0
            if fresh:
                db.execute('INSERT INTO settings VALUES (1,?,?,?,?)', ('Mon entreprise', '', '', int(demo)))
        if fresh and demo:
            self.seed()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def mutate(self, action, payload):
        require(isinstance(payload, dict), 'Requête invalide.')
        handlers = {'products': self.product, 'customers': self.customer, 'stock': self.stock,
                    'sales': self.sale, 'payments': self.payment, 'cancel': self.cancel,
                    'settings': self.settings, 'import': self.import_products}
        require(action in handlers, 'Action inconnue.')
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            request_key = None
            if action in ('payments', 'stock') and payload.get('request_key'):
                request_key = label(payload['request_key'], 'Identifiant', limit=80)
                prior = db.execute('SELECT * FROM operation_requests WHERE request_key=?', (request_key,)).fetchone()
                if prior:
                    require(prior['action'] == action, 'Identifiant déjà utilisé pour une autre action.')
                    db.commit()
                    return json.loads(prior['result'])
            result = handlers[action](db, payload)
            if request_key:
                db.execute('INSERT INTO operation_requests VALUES (?,?,?)', (request_key, action, json.dumps(result)))
            db.commit()
            return result
        except sqlite3.IntegrityError as exc:
            db.rollback()
            if 'products.sku' in str(exc):
                raise ValidationError('Cette référence produit existe déjà.') from exc
            raise ValidationError('Ces données ne peuvent pas être enregistrées.') from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def product(self, db, p):
        fields = (label(p.get('sku'), 'Référence', limit=40), label(p.get('name'), 'Nom'),
                  label(p.get('category', 'Général'), 'Catégorie', limit=60), money(p.get('cost'), "Prix d'achat"),
                  money(p.get('price'), 'Prix de vente'), integer(p.get('minimum', 5), 'Seuil'))
        if p.get('id'):
            pid = integer(p['id'], 'Produit', 1)
            require(db.execute('SELECT id FROM products WHERE id=?', (pid,)).fetchone(), 'Produit introuvable.')
            db.execute('UPDATE products SET sku=?,name=?,category=?,cost=?,price=?,minimum=? WHERE id=?', (*fields, pid))
        else:
            stock = integer(p.get('stock', 0), 'Stock initial')
            pid = db.execute('INSERT INTO products (sku,name,category,cost,price,minimum,stock) VALUES (?,?,?,?,?,?,?)', (*fields, stock)).lastrowid
            if stock:
                db.execute('INSERT INTO movements (product_id,kind,quantity,note,created_at) VALUES (?,?,?,?,?)', (pid, 'opening', stock, 'Stock initial', now()))
        return {'id': pid}

    def customer(self, db, p):
        fields = (label(p.get('name'), 'Nom'), label(p.get('email', ''), 'Email', False),
                  label(p.get('phone', ''), 'Téléphone', False, 40), label(p.get('city', ''), 'Ville', False, 80))
        if p.get('id'):
            cid = integer(p['id'], 'Client', 1)
            require(db.execute('SELECT id FROM customers WHERE id=?', (cid,)).fetchone(), 'Client introuvable.')
            db.execute('UPDATE customers SET name=?,email=?,phone=?,city=? WHERE id=?', (*fields, cid))
        else:
            cid = db.execute('INSERT INTO customers (name,email,phone,city) VALUES (?,?,?,?)', fields).lastrowid
        return {'id': cid}

    def stock(self, db, p):
        pid = integer(p.get('product_id'), 'Produit', 1)
        quantity = integer(p.get('quantity'), 'Quantité', 1)
        kind = p.get('kind', 'receipt')
        require(kind in ('receipt', 'adjustment'), 'Type de mouvement invalide.')
        product = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
        require(product, 'Produit introuvable.')
        delta = quantity if kind == 'receipt' else -quantity
        require(product['stock'] + delta >= 0, 'Stock insuffisant pour cette sortie.')
        require(product['stock'] + delta <= 1_000_000, 'Stock maximum dépassé.')
        note = label(p.get('note', ''), 'Motif', True, 500)
        db.execute('UPDATE products SET stock=stock+? WHERE id=?', (delta, pid))
        db.execute('INSERT INTO movements (product_id,kind,quantity,note,created_at) VALUES (?,?,?,?,?)', (pid, kind, delta, note, now()))
        return {'id': pid}

    def sale(self, db, p):
        key = label(p.get('request_key'), 'Identifiant', limit=80)
        old = db.execute('SELECT id FROM sales WHERE request_key=?', (key,)).fetchone()
        if old:
            return {'id': old['id'], 'already_saved': True}
        items = p.get('items')
        require(isinstance(items, list) and 0 < len(items) <= 100, 'Ajoutez au moins un produit (100 maximum).')
        quantities = {}
        for item in items:
            require(isinstance(item, dict), 'Ligne de vente invalide.')
            pid = integer(item.get('product_id'), 'Produit', 1)
            quantities[pid] = quantities.get(pid, 0) + integer(item.get('quantity'), 'Quantité', 1)
        rows = []
        for pid, quantity in quantities.items():
            product = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
            require(product, 'Un produit est introuvable.')
            require(quantity <= product['stock'], f"Stock insuffisant : {product['name']} ({product['stock']} disponible).")
            rows.append((product, quantity))
        cid = p.get('customer_id') or None
        customer_name = 'Client de passage'
        if cid:
            cid = integer(cid, 'Client', 1)
            customer = db.execute('SELECT * FROM customers WHERE id=?', (cid,)).fetchone()
            require(customer, 'Client introuvable.')
            customer_name = customer['name']
        tax_bps = integer(p.get('tax_bps', 0), 'Taux de taxe', 0, 10000)
        subtotal = sum(product['price'] * qty for product, qty in rows)
        tax = int((Decimal(subtotal) * tax_bps / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        total = subtotal + tax
        paid = money(p.get('paid', 0))
        require(paid <= total, 'Le paiement dépasse le total de la vente.')
        note = label(p.get('note', ''), 'Note', False, 1000)
        method = self.method(p)
        stamp = now()
        sid = db.execute('INSERT INTO sales (request_key,customer_id,customer_name,created_at,subtotal,tax_bps,tax,total,paid,note) VALUES (?,?,?,?,?,?,?,?,?,?)', (key, cid, customer_name, stamp, subtotal, tax_bps, tax, total, paid, note)).lastrowid
        for product, qty in rows:
            db.execute('INSERT INTO sale_items (sale_id,product_id,name,sku,quantity,price,cost) VALUES (?,?,?,?,?,?,?)', (sid, product['id'], product['name'], product['sku'], qty, product['price'], product['cost']))
            db.execute('UPDATE products SET stock=stock-? WHERE id=?', (qty, product['id']))
            db.execute('INSERT INTO movements (product_id,kind,quantity,note,created_at,sale_id) VALUES (?,?,?,?,?,?)', (product['id'], 'sale', -qty, f'Vente VT-{sid:04d}', stamp, sid))
        if paid:
            db.execute('INSERT INTO payments (sale_id,amount,created_at,method) VALUES (?,?,?,?)', (sid, paid, stamp, method))
        return {'id': sid}

    def method(self, p):
        method = p.get('method', 'Espèces')
        require(method in ('Espèces', 'Virement', 'Carte', 'Chèque'), 'Mode de paiement invalide.')
        return method

    def payment(self, db, p):
        sid = integer(p.get('sale_id'), 'Vente', 1)
        sale = db.execute('SELECT * FROM sales WHERE id=?', (sid,)).fetchone()
        require(sale and sale['status'] == 'active', 'Vente introuvable ou annulée.')
        amount = money(p.get('amount'))
        require(0 < amount <= sale['total'] - sale['paid'], 'Le paiement doit être positif et ne pas dépasser le reste dû.')
        db.execute('UPDATE sales SET paid=paid+? WHERE id=?', (amount, sid))
        db.execute('INSERT INTO payments (sale_id,amount,created_at,method) VALUES (?,?,?,?)', (sid, amount, now(), self.method(p)))
        return {'id': sid}

    def cancel(self, db, p):
        sid = integer(p.get('sale_id'), 'Vente', 1)
        sale = db.execute('SELECT * FROM sales WHERE id=?', (sid,)).fetchone()
        require(sale, 'Vente introuvable.')
        if sale['status'] == 'cancelled':
            return {'id': sid}
        require(sale['paid'] == 0, 'Une vente encaissée ne peut pas être annulée ici. Le remboursement nécessite un traitement séparé.')
        for item in db.execute('SELECT * FROM sale_items WHERE sale_id=?', (sid,)).fetchall():
            db.execute('UPDATE products SET stock=stock+? WHERE id=?', (item['quantity'], item['product_id']))
            db.execute('INSERT INTO movements (product_id,kind,quantity,note,created_at,sale_id) VALUES (?,?,?,?,?,?)', (item['product_id'], 'return', item['quantity'], f'Annulation VT-{sid:04d}', now(), sid))
        db.execute("UPDATE sales SET status='cancelled' WHERE id=?", (sid,))
        return {'id': sid}

    def settings(self, db, p):
        db.execute('UPDATE settings SET name=?,address=?,phone=? WHERE id=1',
                   (label(p.get('name'), 'Entreprise'), label(p.get('address', ''), 'Adresse', False, 500), label(p.get('phone', ''), 'Téléphone', False, 40)))
        return {'ok': True}

    def import_products(self, db, p):
        content = label(p.get('csv'), 'CSV', limit=1_000_000).lstrip('\ufeff')
        reader = csv.DictReader(io.StringIO(content))
        expected = {'sku', 'name', 'category', 'cost', 'price', 'stock', 'minimum'}
        require(reader.fieldnames and set(reader.fieldnames) == expected and len(reader.fieldnames) == 7, 'Colonnes attendues : sku,name,category,cost,price,stock,minimum')
        count = 0
        for row in reader:
            count += 1
            require(count <= 5000, 'Maximum 5 000 produits par import.')
            require(None not in row, f'Ligne {count + 1} : trop de colonnes.')
            try:
                self.product(db, row)
            except ValidationError as exc:
                raise ValidationError(f'Ligne {count + 1} : {exc}') from exc
        require(count > 0, 'Le fichier ne contient aucun produit.')
        return {'count': count}

    def state(self):
        db = self.connect()
        try:
            db.execute('BEGIN')
            result = {'settings': dict(db.execute('SELECT * FROM settings WHERE id=1').fetchone())}
            for table in ('products', 'customers', 'sales', 'sale_items', 'payments'):
                result[table] = [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY id DESC')]
            result['movements'] = [dict(row) for row in db.execute('SELECT m.*,p.name,p.sku FROM movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC LIMIT 1000')]
            return result
        finally:
            db.close()

    def backup(self):
        with tempfile.TemporaryDirectory(prefix='atlas-backup-') as directory:
            path = Path(directory) / 'atlas.sqlite3'
            source = self.connect()
            destination = sqlite3.connect(path)
            try:
                source.backup(destination)
            finally:
                source.close()
                destination.close()
            return path.read_bytes()

    def seed(self):
        catalog = [
            ('OUT-001', 'Perceuse à percussion 750 W', 'Outillage', 420, 650, 24, 5),
            ('OUT-002', 'Jeu de tournevis · 6 pièces', 'Outillage', 65, 120, 48, 10),
            ('ELE-001', 'Câble électrique 2,5 mm² · 100 m', 'Électricité', 310, 450, 18, 5),
            ('ELE-002', 'Prise murale double', 'Électricité', 22, 45, 84, 15),
            ('PLO-001', 'Mitigeur de lavabo chromé', 'Plomberie', 180, 320, 4, 5),
            ('QUI-001', 'Vis universelles · boîte de 200', 'Quincaillerie', 25, 55, 65, 10),
            ('PEI-001', 'Peinture blanc mat · 10 L', 'Peinture', 210, 340, 3, 8),
            ('OUT-003', 'Mètre ruban professionnel · 5 m', 'Outillage', 28, 65, 40, 10),
            ('QUI-002', 'Serrure de porte à cylindre', 'Quincaillerie', 85, 150, 0, 5),
            ('PLO-002', 'Flexible de douche · 1,5 m', 'Plomberie', 30, 70, 36, 8),
            ('ELE-003', 'Ampoule LED 12 W', 'Électricité', 12, 30, 120, 20),
            ('OUT-004', 'Marteau de menuisier 500 g', 'Outillage', 45, 95, 22, 5),
        ]
        for sku, name, category, cost, price, stock, minimum in catalog:
            self.mutate('products', dict(sku=sku, name=name, category=category, cost=cost, price=price, stock=stock, minimum=minimum))
        for name, city, phone in [('Bâtir Ensemble', 'Casablanca', '0600 000 001'), ('Atelier Benali', 'Rabat', '0600 000 002'), ('Riad des Oliviers', 'Marrakech', '0600 000 003'), ('Maison & Travaux', 'Casablanca', '0600 000 004'), ('Amine El Fassi', 'Fès', '0600 000 005')]:
            self.mutate('customers', dict(name=name, city=city, phone=phone))
        for i, (pid, qty, cid) in enumerate([(1, 2, 1), (3, 3, 2), (4, 8, 3), (2, 5, 1), (6, 12, 4), (11, 20, 2), (1, 3, 1), (10, 6, 5), (8, 4, 3), (3, 2, 4)]):
            sid = self.mutate('sales', dict(request_key=f'demo-{i}', customer_id=cid, items=[dict(product_id=pid, quantity=qty)], paid=0, tax_bps=0))['id']
            stamp = (datetime.now() - timedelta(days=round(6 * (9 - i) / 9), hours=i % 3)).isoformat(timespec='seconds')
            with closing(self.connect()) as db, db:
                total = db.execute('SELECT total FROM sales WHERE id=?', (sid,)).fetchone()[0]
                paid = total if i % 3 else total // 2
                db.execute('UPDATE sales SET created_at=?,paid=? WHERE id=?', (stamp, paid, sid))
                db.execute('UPDATE movements SET created_at=? WHERE sale_id=?', (stamp, sid))
                db.execute('INSERT INTO payments (sale_id,amount,created_at,method) VALUES (?,?,?,?)', (sid, paid, stamp, 'Virement' if i % 2 else 'Espèces'))


def safe_csv(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, body, status=200, kind='application/json; charset=utf-8', filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            host = self.headers.get('Host', '').lower()
            return host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed():
                return self.respond({'error': 'Accès local uniquement.'}, 403)
            path = self.path.split('?')[0]
            if path == '/api/state':
                return self.respond(store.state())
            if path == '/api/backup':
                return self.respond(store.backup(), kind='application/vnd.sqlite3', filename=f'atlas-{datetime.now():%Y-%m-%d}.sqlite3')
            if path == '/api/export/products':
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['sku', 'name', 'category', 'cost', 'price', 'stock', 'minimum'])
                for p in store.state()['products']:
                    writer.writerow([safe_csv(p['sku']), safe_csv(p['name']), safe_csv(p['category']), f"{p['cost']/100:.2f}", f"{p['price']/100:.2f}", p['stock'], p['minimum']])
                return self.respond(('\ufeff' + output.getvalue()).encode(), kind='text/csv; charset=utf-8', filename='atlas-produits.csv')
            assets = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg', '/platform.js': 'platform.js', '/platform.css': 'platform.css', '/purchases.js': 'purchases.js', '/purchases.css': 'purchases.css', '/accounting.js': 'accounting.js', '/accounting.css': 'accounting.css'}
            if path in assets:
                file = ROOT / 'web' / assets[path]
                return self.respond(file.read_bytes(), kind=mimetypes.guess_type(file)[0] or 'application/octet-stream')
            self.respond({'error': 'Page introuvable.'}, 404)

        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Atlas-Request') != '1':
                return self.respond({'error': 'Requête non autorisée.'}, 403)
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.respond({'error': 'Origine non autorisée.'}, 403)
            try:
                length = int(self.headers.get('Content-Length', 0))
                require(0 < length <= 1_100_000, 'Requête vide ou trop volumineuse.')
                require(self.headers.get('Content-Type', '').split(';')[0] == 'application/json', 'Format JSON attendu.')
                payload = json.loads(self.rfile.read(length))
                require(self.path.startswith('/api/'), 'Action inconnue.')
                self.respond(store.mutate(self.path[5:], payload))
            except (ValidationError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                self.respond({'error': str(exc)}, 400)
            except Exception:
                import traceback
                traceback.print_exc()
                self.respond({'error': "L'enregistrement a échoué. Réessayez."}, 500)

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'atlas.sqlite3')
    parser.add_argument('--empty', action='store_true', help='Create a new database without demonstration data')
    parser.add_argument('--open', action='store_true', help='Open Atlas in your browser')
    args = parser.parse_args()
    store = Store(args.db, demo=not args.empty)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store))
    print(f'Atlas is ready at http://localhost:{args.port} — database: {args.db}', flush=True)
    if args.open:
        import threading
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(f'http://localhost:{args.port}')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
