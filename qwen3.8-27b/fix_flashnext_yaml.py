import re, sys

p = sys.argv[1]
s = open(p).read()

# Double up shell-interpolated $ in the command: block
in_command = False
out = []
for line in s.split("\n"):
    if re.match(r"^    command:", line):
        in_command = True
    elif re.match(r"^    (environment|volumes|deploy|healthcheck|networks):", line):
        in_command = False
    if in_command:
        # Double $ that are followed by {, (, or a word char
        line = re.sub(r"\$(?=[{(\w])", "$$", line)
    out.append(line)
s = "\n".join(out)

# Fix the guarded-array expansion: ${MTP_ARGS[@]+"${MTP_ARGS[@]}"}
# After doubling: $${MTP_ARGS[@]+"${MTP_ARGS[@]}"}  -> want: $${MTP_ARGS[@]+$$"$$"}
s = s.replace('$${MTP_ARGS[@]+"${MTP_ARGS[@]}"', '$${MTP_ARGS[@]+$$"$$"')

open(p, "w").write(s)
print("done")
