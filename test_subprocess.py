import subprocess

result=subprocess.run(["ls","-al"],capture_output=True)
print(result)