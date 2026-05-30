import os

filename = 'draft_wc_design/screens-status.jsx'

with open(filename, 'r', encoding='utf-8') as f:
    content = f.read()

stack = []
in_string = False
string_char = None
in_comment = False
in_multiline_comment = False

i = 0
n = len(content)
line = 1
col = 1

while i < n:
    char = content[i]
    
    if char == '\n':
        line += 1
        col = 1
        if in_comment:
            in_comment = False
        i += 1
        continue
        
    if in_comment:
        i += 1
        col += 1
        continue
        
    if in_multiline_comment:
        if char == '*' and i + 1 < n and content[i+1] == '/':
            in_multiline_comment = False
            i += 2
            col += 2
        else:
            i += 1
            col += 1
        continue
        
    if in_string:
        if char == '\\':
            i += 2
            col += 2
            continue
        if char == string_char:
            in_string = False
        i += 1
        col += 1
        continue
        
    # Comments check
    if char == '/' and i + 1 < n and content[i+1] == '/':
        in_comment = True
        i += 2
        col += 2
        continue
    if char == '/' and i + 1 < n and content[i+1] == '*':
        in_multiline_comment = True
        i += 2
        col += 2
        continue
        
    # String checks
    if char in ['"', "'", '`']:
        in_string = True
        string_char = char
        i += 1
        col += 1
        continue
        
    # Braces & Parens stack tracking
    if char in ['{', '(', '[']:
        stack.append((char, line, col))
    elif char in ['}', ')', ']']:
        if not stack:
            print(f"Excess closing {char} at line {line}, col {col}")
        else:
            top_char, top_line, top_col = stack[-1]
            match = (top_char == '{' and char == '}') or \
                    (top_char == '(' and char == ')') or \
                    (top_char == '[' and char == ']')
            if match:
                stack.pop()
            else:
                print(f"Mismatched closing {char} at line {line}, col {col}. Opened as {top_char} at line {top_line}, col {top_col}")
                stack.pop()
                
    i += 1
    col += 1

print("\n--- Remaining Unclosed Brackets in Stack ---")
for char, l, c in stack:
    print(f"Unclosed '{char}' opened at line {l}, col {c}")
