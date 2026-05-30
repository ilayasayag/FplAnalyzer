import os

files = [
    'draft_wc_design/screens-status.jsx',
    'draft_wc_design/screens-bracket.jsx',
    'draft_wc_design/app.jsx',
    'draft_wc_design/firebase.jsx'
]

for filename in files:
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        continue
        
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
        
    braces = 0
    parens = 0
    brackets = 0
    
    # Simple state machine to skip comments and strings
    in_string = False
    string_char = None
    in_comment = False
    in_multiline_comment = False
    
    i = 0
    n = len(content)
    
    while i < n:
        char = content[i]
        
        if in_comment:
            if char == '\n':
                in_comment = False
            i += 1
            continue
            
        if in_multiline_comment:
            if char == '*' and i + 1 < n and content[i+1] == '/':
                in_multiline_comment = False
                i += 2
            else:
                i += 1
            continue
            
        if in_string:
            if char == '\\':
                i += 2
                continue
            if char == string_char:
                in_string = False
            i += 1
            continue
            
        # Comments check
        if char == '/' and i + 1 < n and content[i+1] == '/':
            in_comment = True
            i += 2
            continue
        if char == '/' and i + 1 < n and content[i+1] == '*':
            in_multiline_comment = True
            i += 2
            continue
            
        # String checks
        if char in ['"', "'", '`']:
            in_string = True
            string_char = char
            i += 1
            continue
            
        # Braces & Parens counts
        if char == '{': braces += 1
        elif char == '}': braces -= 1
        elif char == '(': parens += 1
        elif char == ')': parens -= 1
        elif char == '[': brackets += 1
        elif char == ']': brackets -= 1
        
        i += 1
        
    print(f"File: {filename}")
    print(f"  Braces count: {braces} (mismatch if != 0)")
    print(f"  Parens count: {parens} (mismatch if != 0)")
    print(f"  Brackets count: {brackets} (mismatch if != 0)")
