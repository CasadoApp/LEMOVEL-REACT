import os
import re

dao_dir = 'API/Fontes/Source/Model/DAO'
daos = []

for root, _, files in os.walk(dao_dir):
    for f in files:
        if f.endswith('.pas'):
            daos.append(os.path.join(root, f))

# regex for finding assignments like: Result.idEmpresa := ADataSet.FieldByName('emp_001').AsInteger;
field_pattern = re.compile(r'ADataSet\.FieldByName\(\'([\w_]+)\'\)\.(As\w+)', re.IGNORECASE)

sql_types_map = {
    'AsInteger': 'INT',
    'AsString': 'VARCHAR(255)',
    'AsCurrency': 'DECIMAL(15, 2)',
    'AsFloat': 'DOUBLE',
    'AsDateTime': 'DATETIME',
    'AsBoolean': 'BOOLEAN',
    'AsBytes': 'LONGBLOB'
}

def guess_type_from_name(col_name):
    lower_col = col_name.lower()
    if lower_col.startswith('b_'):
        return 'BOOLEAN'
    if lower_col.startswith('id_') or lower_col.startswith('emp_') or lower_col.startswith('mat_') or lower_col.startswith('cat_') or lower_col.startswith('usu_') or lower_col.startswith('mes_') or lower_col.startswith('com_'):
        return 'INT'
    if 'data' in lower_col or 'hora' in lower_col:
        return 'DATETIME'
    if 'valor' in lower_col or 'taxa' in lower_col or 'preco' in lower_col or 'desconto' in lower_col or 'custo' in lower_col or 'total' in lower_col or 'quantidade' in lower_col or lower_col.startswith('qtd') or 'rendimento' in lower_col or 'estoque' in lower_col:
        return 'DECIMAL(15, 2)'
    return 'VARCHAR(255)'

tables = {}

for dao_file in daos:
    with open(dao_file, 'r', encoding='latin1') as f:
        content = f.read()

    # Find explicit field assignments to capture explicit types
    field_types = {}
    for match in field_pattern.finditer(content):
        col, dtype = match.groups()
        field_types[col.lower()] = sql_types_map.get(dtype, 'VARCHAR(255)')

    # Extract all .SQL('...') arguments safely
    sql_parts = []
    # match anything inside .SQL('...') or Query.SQL('...')
    for stmt_match in re.finditer(r"(?i)(?:Query|FQuery)?\.SQL\('([^']*)'\)", content):
        sql_parts.append(stmt_match.group(1))

    full_sql = " ".join(sql_parts)

    tname = "UnknownTable"

    # Extract table name from FROM clause
    # Avoid picking up table names from JOIN clauses if possible, just the primary FROM
    from_matches = re.findall(r'(?i)\bfrom\s+([a-zA-Z_0-9]+)', full_sql)
    if not from_matches:
        # fallback to raw content
        from_matches = re.findall(r'(?i)\bfrom\s+([a-zA-Z_0-9]+)', content)

    if from_matches:
        tname = from_matches[0].lower()
        if tname == 'information_schema' or tname == 'unknowntable':
            if 'vendaitem' in dao_file.lower(): tname = 'vendaitem'
            elif 'venda' in dao_file.lower(): tname = 'venda'
            else: tname = 'UnknownTable'

    if tname == 'unknowntable': continue
    if tname not in tables:
        tables[tname] = {}

    # Extracting columns strictly from FieldByName bindings is much safer than parsing raw SELECT statements
    # because sub-queries and functions create impossible garbage in string-split routines.
    # However, you mentioned `b_controle_opc` was missing because it's only in SELECT, not in FieldByName.
    # Let's cleanly extract just simple words separated by commas in the SELECT block.

    # find SELECT <everything before FROM>
    select_match = re.search(r'(?i)select\s+(.*?)\s+from\s+', full_sql, re.DOTALL)
    if select_match:
        select_clause = select_match.group(1)

        # Remove anything inside parenthesis to kill subqueries and function calls
        # We need a small loop because of nested parens
        while True:
            new_select = re.sub(r'\([^()]*\)', '', select_clause)
            if new_select == select_clause: break
            select_clause = new_select

        # Now we should have a relatively clean list of columns, maybe with AS aliases.
        parts = select_clause.split(',')
        for p in parts:
            p = p.strip()
            if not p: continue

            # Check for alias
            as_match = re.search(r'(?i)\s+as\s+([a-zA-Z_0-9]+)', p)
            if as_match:
                col = as_match.group(1).lower()
            else:
                # If no alias, it's just the column, maybe prefixed with table.
                # Just take the last valid alphanumeric token.
                tokens = re.findall(r'[a-zA-Z_0-9]+', p)
                if tokens:
                    col = tokens[-1].lower()
                else:
                    continue

            # Skip noise words and long strings
            if col in ('true', 'false', 'null', 'select', 'from', 'where', 'and', 'or', 'case', 'when', 'then', 'end', 'else'): continue
            if col.isdigit(): continue
            if len(col) > 64: continue # MySQL identifier max length is 64

            dtype = field_types.get(col, guess_type_from_name(col))
            tables[tname][col] = dtype

    # Add back explicit FieldByName bindings (they are always correct)
    for col, dtype in field_types.items():
        if col not in tables[tname]:
            tables[tname][col] = dtype


# Generate SQL
with open('db_schema.sql', 'w') as out_f:
    out_f.write("-- Database schema recreated from Delphi DAO models (V4 - strict clean SQL parsing)\n\n")

    for tname, columns in tables.items():
        if tname == 'unknowntable' or not columns: continue
        out_f.write(f"CREATE TABLE `{tname}` (\n")
        col_defs = []
        for col, dtype in columns.items():
            col_defs.append(f"    `{col}` {dtype}")

        out_f.write(",\n".join(col_defs))
        out_f.write("\n);\n\n")

print("Generated db_schema.sql securely.")
