import sqlite3, os

db = os.path.expanduser('~/.gemini/antigravity/conversation_summaries.db')
conn = sqlite3.connect(db)
# Pega uma conversa de Patrimonio que tem project_id ac18ca3d-99c4-48fe-a717-6a80f9bafd86 ORIGINAL
row = conn.execute("SELECT conversation_id, raw_summary FROM conversation_summaries WHERE project_id = 'ac18ca3d-99c4-48fe-a717-6a80f9bafd86' AND raw_summary LIKE '%ac18ca3d%' LIMIT 1").fetchone()
cid, blob = row

def parse_protobuf(data, depth=0):
    i = 0
    indent = "  " * depth
    while i < len(data):
        val = 0
        shift = 0
        while True:
            if i >= len(data): return
            b = data[i]
            i += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        field_num = val >> 3
        wire_type = val & 0x07
        if wire_type == 0:
            v = 0; s = 0
            while True:
                b = data[i]; i += 1
                v |= (b & 0x7F) << s
                if not (b & 0x80): break
                s += 7
            print(f"{indent}Field {field_num}: varint {v}")
        elif wire_type == 2:
            length = 0; s = 0
            while True:
                b = data[i]; i += 1
                length |= (b & 0x7F) << s
                if not (b & 0x80): break
                s += 7
            content = data[i:i+length]
            i += length
            try:
                text = content.decode('utf-8')
                is_printable = all(c.isprintable() or c in '\r\n\t ' for c in text)
                if is_printable:
                    print(f"{indent}Field {field_num} (len {length}): string = {text[:80]}")
                else:
                    raise ValueError()
            except Exception:
                print(f"{indent}Field {field_num} (len {length}): sub-message")
                parse_protobuf(content, depth + 1)
        elif wire_type == 1:
            i += 8
        elif wire_type == 5:
            i += 4
        else:
            break

print(f"=== {cid} ===")
parse_protobuf(blob)
