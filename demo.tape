# Records the reproduction loop as a GIF.
#
#   vhs demo.tape
#
# Uses --mock so the recording is deterministic and costs no GPU or sandbox
# time. The canned responses describe the same bug a live run reproduces.

Output demo.gif

Set FontSize 15
Set Width 1300
Set Height 850
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 25ms

Type "cat issue.txt"
Enter
Sleep 3s

Type "python -m src.main --repo https://github.com/Gauntlet-HQ/yes-build-me.git --ref 079886d --issue issue.txt --mock"
Enter
Sleep 6s

Type "cat outputs/attempt-2/reproduce.spec.js"
Enter
Sleep 7s
