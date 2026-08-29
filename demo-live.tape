# Records a real run of the reproduction loop as a GIF.
#
#   vhs demo-live.tape
#
# Replays a captured live run rather than executing one, because a real run
# spends most of its wall clock cloning the repository, installing dependencies
# and downloading a browser. The output is verbatim; only the waiting is
# removed. See scripts/replay.sh for how to regenerate the capture.

Output demo-live.gif

Set FontSize 15
Set Width 1300
Set Height 900
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 25ms

Type "cat issue.txt"
Enter
Sleep 3s

Type "scripts/replay.sh demo-live.log"
Enter
Sleep 14s

Type "cat outputs/attempt-2/reproduce.spec.ts"
Enter
Sleep 8s
