content = """A
B
C
D
E
A
B
C
D
EA
B
C
D
E
A
B
C
D
E

A
B
C
D
E
A
B
C
D
EA
B
C
D
E
A
B
C
D
E

A
B
C
D
E
A
B
C
D
EA
B
C
D
E
A
B
C
D
E"""

split_content = content.split("\n\n")
print(split_content)
final_content = []

for paragraph in split_content:
    lines = paragraph.split("\n")
    for i in range(0, len(lines), 10):
        final_content.append("\n".join(lines[i:i+10]))
print(final_content)
split_content = final_content
print(split_content)
