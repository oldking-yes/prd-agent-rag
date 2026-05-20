import re

fp = 'd:/桌面/Claude Code/prd_agent_rag/frontend/index.html'
with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# Check the prompt-grid section
prompt_idx = content.find('prompt-grid')
if prompt_idx > 0:
    surround = content[prompt_idx-200:prompt_idx+600]
    print(surround[:600])

# Check for common issues:
# 1. Unescaped backticks
bc_count = content.count('`')
print(f'\nBacktick count: {bc_count} (should be even: {bc_count % 2 == 0})')

# 2. Check if the prompt chips have proper string
if '锟' in content:
    idx = content.find('锟')
    print(f'Corrupted char at {idx}: {content[idx-20:idx+20]}')

# Verify script block structure
script_start = content.find('<script type="text/babel">')
script_end = content.find('</script>', script_start)
babel_script = content[script_start:script_end]
print(f'\nBabel script: {script_start} to {script_end} ({len(babel_script)} chars)')

# Check for unclosed JSX/React elements in the tutorial block
tutorial_start = content.find("message-list-empty tutorial")
if tutorial_start > 0:
    # Find the actual react createElement block
    create_el = content.find("React.createElement", tutorial_start - 200)
    if create_el > 0:
        print(f'\nTutorial starts at React.createElement: {create_el}')
        # Count depth by following parens
        depth = 0
        for i in range(create_el, min(create_el + 10000, len(content))):
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
                if depth == 0:
                    print(f'Tutorial block closes at: {i} (child of ternary)')
                    break
        print(f'Depth at 10000 chars: {depth}')
