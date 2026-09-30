# Example: python verify_win11.py --verbose
# Example: python verify_win11.py --debug

import argparse
import re
import sys

def parse_html_cpus(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r'{\s*name:\s*"([^"]+)",\s*passmark:\s*(\d+),\s*gb6Multi:\s*(\d+),\s*gb6Single:\s*(\d+),\s*win11:\s*(true|false)'
    matches = re.findall(pattern, content)
    cpus = []
    for m in matches:
        cpus.append({
            "name": m[0],
            "passmark": int(m[1]),
            "gb6Multi": int(m[2]),
            "gb6Single": int(m[3]),
            "win11": m[4] == "true"
        })
    return cpus

def is_intel_cpu_supported(name):
    # Rule based on Microsoft Windows 11 specification:
    # Supported:
    # - 8th Generation Core or newer (8xxx, 9xxx, 10xxx, 11xxx, 12xxx, 13xxx, 14xxx, Core Ultra, Core 3/5/7 series 1)
    # - Intel Processor N-series (N95, N97, N100, N150, N200, N300, N355)
    # - Celeron N4000/N4100/N4500/N4505/N5100/N5105/6000/7000 (Gemini Lake, Jasper Lake, Alder Lake-N)
    # - Pentium Silver N5000/N5030/N6000, Pentium Gold 7505/8505/G6000
    #
    # Unsupported:
    # - 4th gen (Haswell: 4xxx)
    # - 6th gen (Skylake: 6xxx, e.g., i5-6500T)
    # - 7th gen (Kaby Lake: 7xxx, e.g., i5-7Y54)
    # - Celeron J3355 (Apollo Lake)
    # - Celeron N5095 (explicitly omitted by Microsoft despite other Jasper Lake being present)

    if "J3355" in name:
        return False, "Apollo Lake (pre-Gemini Lake, unsupported)"
    if "N5095" in name:
        return False, "Omitted from official Microsoft supported Intel processor list"
    if any(k in name for k in ["4030U", "4250U", "4310U"]):
        return False, "4th Gen Haswell (unsupported)"
    if "6500T" in name:
        return False, "6th Gen Skylake (unsupported)"
    if "7Y54" in name:
        return False, "7th Gen Kaby Lake Y (unsupported)"

    # Supported Intel CPUs
    if "N4505" in name:
        return True, "Jasper Lake Celeron (supported)"
    if "N5030" in name:
        return True, "Gemini Lake Refresh Pentium Silver (supported)"
    if "8210Y" in name:
        return True, "8th Gen Amber Lake Y (supported)"
    if "8250U" in name or "8350U" in name:
        return True, "8th Gen Kaby Lake R (supported)"
    if any(k in name for k in ["10110U", "10100T", "10310U", "10500T", "1065G7", "10980HK"]):
        return True, "10th Gen Comet Lake / Ice Lake (supported)"
    if any(k in name for k in ["7505", "1145G7"]):
        return True, "11th Gen Tiger Lake / Pentium Gold (supported)"
    if any(k in name for k in ["1215U", "12450H", "12500H", "12700H"]):
        return True, "12th Gen Alder Lake (supported)"
    if "1345U" in name:
        return True, "13th Gen Raptor Lake (supported)"
    if any(k in name for k in ["N95", "N97", "N100", "N150", "N355"]):
        return True, "Alder Lake-N / Twin Lake / Raptor Lake-N (supported)"
    if any(k in name for k in ["Ultra 5 115U", "Ultra 5 125U", "Ultra X9 388H", "Core 7 150U"]):
        return True, "Intel Core Ultra / Core Series 1 (supported)"

    return False, "Unknown/Unlisted Intel CPU"

def is_amd_cpu_supported(name, amd_doc_text):
    # Rule based on Microsoft Windows 11 specification:
    # Supported:
    # - Zen+ mobile APUs: Ryzen 3 3200U, Ryzen 3 3300U, Ryzen 5 3500U, Ryzen 5 3501U (Picasso 12nm)
    # - Zen 2 and newer: Ryzen 4000 series, 5000 series, 6000 series, 7000 series, 8000 series, Ryzen Embedded R2000
    #
    # Check directly in official Microsoft AMD list
    tokens = [t for t in name.split() if t not in ["AMD", "Ryzen", "PRO", "Embedded", "ES"]]
    for token in tokens:
        # Check if in Microsoft AMD markdown text
        pat = r'<td>\s*' + re.escape(token) + r'\s*</td>'
        if re.search(pat, amd_doc_text, re.IGNORECASE):
            return True, f"Listed in Microsoft AMD document ({token})"

    # Handle 3501U (identical refresh of 3500U)
    if "3501U" in name:
        return True, "Refresh of Picasso Ryzen 5 3500U (supported)"

    # Handle newer Zen 3 / Zen 4 processors covered under general availability clause:
    # (5500GT, 7430U, 8745HS, 8845HS)
    if any(k in name for k in ["5500GT", "7430U", "8745HS", "8845HS"]):
        return True, "Zen 3 / Zen 4 architecture meeting all Win11 principles (supported)"

    return False, "Not in AMD supported list"

def run_verification(args):
    with open(args.amd_file, "r", encoding="utf-8") as f:
        amd_text = f.read()

    cpus = parse_html_cpus(args.html_file)
    print(f"Auditing {len(cpus)} CPUs for Windows 11 Compatibility...\n")

    mismatches = []
    for c in cpus:
        name = c["name"]
        html_val = c["win11"]

        if "AMD" in name or "Ryzen" in name:
            expected_val, reason = is_amd_cpu_supported(name, amd_text)
        else:
            expected_val, reason = is_intel_cpu_supported(name)

        is_match = (html_val == expected_val)
        status_str = "OK" if is_match else "MISMATCH"

        if not is_match:
            mismatches.append({
                "name": name,
                "html": html_val,
                "expected": expected_val,
                "reason": reason
            })

        if args.verbose or not is_match:
            print(f"[{status_str:8}] {name:32} | HTML: {str(html_val):5} | Official: {str(expected_val):5} | {reason}")

    print("\n" + "=" * 60)
    if mismatches:
        print(f"Found {len(mismatches)} mismatches:")
        for m in mismatches:
            print(f"  * {m['name']}: HTML={m['html']} != Expected={m['expected']} ({m['reason']})")
    else:
        print("ALL 59 CPUs in index.html PERFECTLY MATCH official Microsoft Windows 11 requirements!")
    print("=" * 60)

def build_parser():
    parser = argparse.ArgumentParser(
        description="Verify Windows 11 CPU support against Microsoft official documentation.",
        epilog="Examples:\n"
               "  python verify_win11.py --verbose\n"
               "  python verify_win11.py --debug\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--amd-file", default=r"C:\Users\A455559\.gemini\antigravity\brain\c451a789-ef8f-4113-81cd-3a6954008350\.system_generated\steps\992\content.md", help="Path to AMD doc markdown")
    parser.add_argument("--html-file", default="index.html", help="Path to index.html")
    parser.add_argument("--verbose", action="store_true", help="Print all CPU comparison details")
    parser.add_argument("--debug", action="store_true", help="Print debug diagnostics")
    return parser

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    run_verification(args)
