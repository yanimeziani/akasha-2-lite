import os
import sys

from manifesto_part1 import get_text_part1
from manifesto_part2 import get_text_part2
from manifesto_part3 import get_text_part3
from manifesto_part4 import get_text_part4
from manifesto_part5 import get_text_part5
from manifesto_supplements import get_supplements

def main():
    parts = [
        get_text_part1(),
        get_text_part2(),
        get_text_part3(),
        get_text_part4(),
        get_supplements(),
        get_text_part5()
    ]
    full_document = "\n\n".join(parts)
    lines = full_document.splitlines()
    print(f"Total compiled lines: {len(lines)}")
    
    # Paths to write
    doc_path = "/Users/instant/Dev/akasha-2-lite/docs/AKASHA_2_RAW_CONCEPT.md"
    artifact_path = "/Users/instant/.gemini/antigravity-cli/brain/4df34025-62b1-47cd-9e08-c2193015481f/AKASHA_2_RAW_CONCEPT.md"
    
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(full_document)
    print(f"Wrote to {doc_path}")

    with open(artifact_path, "w", encoding="utf-8") as f:
        f.write(full_document)
    print(f"Wrote to {artifact_path}")

if __name__ == "__main__":
    main()
