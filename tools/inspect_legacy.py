#!/usr/bin/env python3
"""Read-only PE inventory. Run from the workspace root; never executes binaries."""
import collections
import hashlib
import json
import math
import re
import struct
from pathlib import Path


def inspect(path):
    data = path.read_bytes()
    result = {'file': path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if not data:
        result['status'] = 'empty placeholder'
        return result
    if data[:2] != b'MZ' or len(data) < 64:
        result['status'] = 'not a recognized PE file'
        return result
    pe = struct.unpack_from('<I', data, 60)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        result['status'] = 'invalid PE signature'
        return result
    count = struct.unpack_from('<H', data, pe + 6)[0]
    sections = pe + 24 + struct.unpack_from('<H', data, pe + 20)[0]
    end = max(sum(struct.unpack_from('<II', data, sections + i * 40 + 16)) for i in range(count))
    overlay = data[end:]
    entropy = -sum(n / len(overlay) * math.log2(n / len(overlay)) for n in collections.Counter(overlay).values()) if overlay else 0
    result.update(
        pe_machine=hex(struct.unpack_from('<H', data, pe + 4)[0]),
        overlay_offset=end, overlay_bytes=len(overlay), overlay_entropy=round(entropy, 4),
        foxpro_payload_offsets=[match.start() for match in re.finditer(b'\xfe\xf2\xee', data)][:20],
        utf16_strings=[match.group().decode('utf-16-le') for match in re.finditer(rb'(?:[\x20-\x7e]\x00){5,}', data)][:70],
    )
    return result


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    output = root / 'analysis' / 'binary-inventory.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps([inspect(p) for p in sorted(root.glob('*.exe'))], indent=2, ensure_ascii=False) + '\n')
    print(output)
