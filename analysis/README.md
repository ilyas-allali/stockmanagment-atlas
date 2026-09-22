# Atlascom executable analysis

This is a static analysis of the files supplied in this workspace. No original executable was run or modified. The new Atlas application is an independent implementation; it does not contain recovered Atlascom code.

## Confirmed from the files

- Five nonempty Windows executables are present: Atlascom, Atlascompta, Liasse, TVA, and Transfert, with ` (1)` in their filenames. The five files without that suffix are empty placeholders.
- All nonempty files are 32-bit x86 Windows GUI executables.
- Atlascom contains `VisualFoxProRuntime.9`, `VFP9R.DLL`, `VFP9T.DLL`, and a Visual FoxPro manifest.
- Atlascom version metadata: product `Atlascom`, file/product version `5.84.0`, company `DYNA INFO`, original filename `atlascomys.exe`.
- Its PE sections end at `0x9e00` (40,448 bytes). The remaining payload begins `fe f2 ee 96 07 94 0c 63 91`.
- Payload entropy is approximately 7.9998 bits/byte. This is consistent with compressed or encrypted content, but does not identify a particular protection mechanism.
- No companion DBF/FPT/CDX/DBC data, FoxPro project files, or source files were supplied.
- The PE loader timestamp is not reliable evidence of the application's release date.

Full sizes, hashes, offsets, and readable version-resource strings are recorded in `binary-inventory.json`. Reproduce the inventory with:

```sh
python3 tools/inspect_legacy.py
```

## Recovery attempt

[FoxLift](https://foxlift.dev/), version 0.6.0, was installed into a temporary analysis directory and used locally. Its documented `inspect` and `extract` commands were attempted against the original Atlascom executable. The binary was not uploaded to an external service.

- Inspection found zero parseable compiled modules and zero statements (`foxlift-inspect.json`).
- Extraction refused the payload header at the derived overlay base (`foxlift-extract.log`).
- No forms, tables, business rules, report layouts, or source code were recovered.

```sh
PYTHONPATH=/tmp/atlascom-analysis-tools python3 -m foxlift inspect 'atlascom (1).exe' --json
PYTHONPATH=/tmp/atlascom-analysis-tools python3 -m foxlift extract 'atlascom (1).exe' -o analysis/recovered --json
```

The [Foxpert FXP format notes](https://foxpert.com/docs/fxp.en.htm) describe the usual `FE F2 FF` compiled-module marker. Finding a different APP payload and no parsable modules is a limitation of this recovery attempt, not evidence that the original application contains no functionality. Full behavioral reconstruction would need a runnable installation and its runtime/data, or another compatible decompiler.

## Decisions for the replacement

The user selected stock and sales and explicitly allowed a different, improved implementation. Atlas therefore implements newly authored product, customer, sale, payment, stock-history, CSV, and backup workflows. French, MAD currency, integer stock quantities, and the sample hardware-store catalog are design choices, not recovered business rules. Sample products and customers are fictional. Original stock levels, transactions, tax logic, accounting integrations, licensing, and legacy report definitions have not been migrated.
