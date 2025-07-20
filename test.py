import subprocess

returna = subprocess.run(
    ["osascript",
    "-e",
    'display dialog "Test dialog" buttons {"No", "Yes"} default button "Yes"'],
    capture_output=True, text=True)

print(returna)
if "returned:No" in str(returna):
    print("you're all gay")