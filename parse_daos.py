import os
import re

dao_dir = 'API/Fontes/Source/Model/DAO'
daos = []

for root, _, files in os.walk(dao_dir):
    for f in files:
        if f.endswith('.pas'):
            daos.append(os.path.join(root, f))

# regex for finding assignments like: Result.idEmpresa := ADataSet.FieldByName('emp_001').AsInteger;
field_pattern = re.compile(r'Result(?:\.[\w_]+)*\s*:=\s*ADataSet\.FieldByName\(\'([\w_]+)\'\)\.(As\w+)', re.IGNORECASE)

tables_info = {}

for dao_file in daos:
    with open(dao_file, 'r', encoding='latin1') as f:
        content = f.read()

    fields = []
    # Avoid duplicate fields in the same table
    seen_fields = set()
    for match in field_pattern.finditer(content):
        col, dtype = match.groups()
        # lowercase to unify
        col_lower = col.lower()
        if col_lower not in seen_fields:
            fields.append((col, dtype))
            seen_fields.add(col_lower)

    if fields:
        # try to find table name
        table_pattern = re.compile(r'\.SQL\(\'[^\']*?from\s+([a-zA-Z_0-9]+)[^\']*\'\)', re.IGNORECASE)
        table_match = table_pattern.search(content)
        table_name = "UnknownTable"
        if table_match:
            table_name = table_match.group(1)

        tables_info[dao_file] = {
            'table': table_name,
            'fields': fields
        }

# Generate SQL script
sql_types_map = {
    'AsInteger': 'INT',
    'AsString': 'VARCHAR(255)',
    'AsCurrency': 'DECIMAL(15, 2)',
    'AsFloat': 'DOUBLE',
    'AsDateTime': 'DATETIME',
    'AsBoolean': 'BOOLEAN',
    'AsBytes': 'LONGBLOB'
}

with open('db_schema.sql', 'w') as out_f:
    out_f.write("-- Database schema recreated from Delphi DAO models\n\n")

    # We want to uniquely identify tables as some DAOs might query the same table or have aliases
    tables = {}
    for dao, info in tables_info.items():
        tname = info['table'].lower()
        if tname == 'information_schema' or tname == 'unknowntable':
            if 'VendaItem' in dao: tname = 'vendaitem'
            else: continue

        if tname not in tables:
            tables[tname] = {}

        for col, dtype in info['fields']:
            if col.lower() not in tables[tname]:
                tables[tname][col.lower()] = {
                    'name': col,
                    'type': sql_types_map.get(dtype, 'VARCHAR(255)')
                }

    for tname, columns in tables.items():
        out_f.write(f"CREATE TABLE `{tname}` (\n")
        col_defs = []
        for col_lower, col_info in columns.items():
            col_defs.append(f"    `{col_info['name']}` {col_info['type']}")

        out_f.write(",\n".join(col_defs))
        out_f.write("\n);\n\n")

print("Generated db_schema.sql")
