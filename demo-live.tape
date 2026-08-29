# Records a real run of the reproduction loop as a GIF.
#
#   vhs demo-live.tape
#
# Replays the captured output of a live run rather than executing one, because
# a real run spends most of its wall clock cloning the repository, installing
# dependencies and downloading a browser. The output in demo-live.log is
# verbatim; only the waiting is removed. See scripts/replay.sh.

Output demo-live.gif

Set FontSize 15
Set Width 1300
Set Height 800
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 25ms

Type "cat issue.txt"
Enter
Sleep 4s

Type "scripts/replay.sh demo-live.log"
Enter
Sleep 20s
