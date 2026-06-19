import io
import csv

def test_parse_csv(file_bytes):
    try:
        decoded = file_bytes.decode('utf-8', errors='ignore')
        print("Decoded length:", len(decoded))
        print("Contains NUL:", '\x00' in decoded)
        
        reader = csv.reader(io.StringIO(decoded))
        rows = []
        for i, row in enumerate(reader):
            if any(row):
                rows.append(", ".join(row))
        print(f"Parsed {len(rows)} rows successfully.")
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e))

# Simulate a UTF-16 encoded CSV file (which contains NUL bytes when interpreted as UTF-8)
utf16_content = "ID,Nombre,Email\n1,Miguel,miguel@example.com".encode('utf-16')
print("--- Testing UTF-16 bytes decoded as UTF-8 ---")
test_parse_csv(utf16_content)
