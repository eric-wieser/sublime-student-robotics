import os
WINDOWS = os.name == 'nt'
import sublime
import sublime_plugin
import os.path as path
import string
import tempfile
import shutil
import datetime
import zipfile
if WINDOWS:
	import ctypes

class DeployZipCommand(sublime_plugin.WindowCommand):
	def __init__(self, *args, **kwargs):
		self.tmpd = None
		sublime_plugin.WindowCommand.__init__(self, *args, **kwargs)

	def makeZip(self, userCodePath, pyenvPath, ignore):
		self.tmpd = tempfile.mkdtemp(suffix="-sr")

		ignore = shutil.ignore_patterns(*ignore)
		zipContents = path.join(self.tmpd, "robot_zip")
		zipLocation = path.join(self.tmpd, "robot.zip")
		shutil.copytree(pyenvPath, zipContents, ignore=ignore)

		# Copy in the user's code
		shutil.copytree(
			userCodePath,
			path.join(zipContents, "user"),
			ignore = ignore
		)

		#shutil.make_archive(path.join(self.tmpd, "robot"), "zip", self.tmpd)

		zip = zipfile.ZipFile(zipLocation, 'w', zipfile.ZIP_DEFLATED)
		rootlen = len(zipContents) + 1
		for base, dirs, files in os.walk(zipContents):
		    for file in files:
		        fn = path.join(base, file)
		        zip.write(fn, fn[rootlen:])
		zip.close()

		return zipLocation

	def getDrives(self):
		if WINDOWS:
			def getDriveName(letter):
				volumeNameBuffer = ctypes.create_unicode_buffer(512)
				fileSystemNameBuffer = ctypes.create_unicode_buffer(512)

				ctypes.windll.kernel32.GetVolumeInformationW(
					ctypes.c_wchar_p(letter),
					volumeNameBuffer, ctypes.sizeof(volumeNameBuffer),
					None, None, None,
					fileSystemNameBuffer, ctypes.sizeof(fileSystemNameBuffer)
				)

				return volumeNameBuffer.value

			ctypes.windll.kernel32.SetErrorMode(1)
			driveBits = ctypes.windll.kernel32.GetLogicalDrives()
			return [
				{
					"path": letter + ":\\",
					"name": getDriveName(letter + ":\\")
				}
				for i, letter in enumerate(string.uppercase)
				if (driveBits >> i) & 1
			]
		else:
			return [
				{
					"path": path.join('/media', name),
					"name": None
				}
				for name in os.listdir('/media')
			]
		


	def run(self):
		s = sublime.load_settings("Student Robotics.sublime-settings")
		pyenvLocation = path.join(s.get('pyenv-location'), 'pyenv')
		ignorePatterns = s.get('ignore')
		
		drives = self.getDrives()
		
		if not drives:
			sublime.status_message("No memory stick!")
			return

		for drive in drives:
			drive["srobo"] = path.exists(path.join(drive["path"], ".srobo"))#
			try:
				drive["last-deployed"] = datetime.datetime.fromtimestamp(path.getmtime(path.join(drive["path"], "robot.zip")))
			except:
				drive["last-deployed"] = None


		drives.sort(key=lambda a: a["srobo"], reverse=True)

		userPaths = [
			folder
			for folder in self.window.folders()
			if path.exists(path.join(folder, '.git')) and path.exists(path.join(folder, 'robot.py'))
		]
		
		if not userPaths:
			sublime.status_message("Can't find source code")
			return
		
		sublime.status_message("Exporting from %s..."%userPaths[0])
		
		#Build the messages for the quickpanel
		messages = []
		for drive in drives:			
			title = "Deploy to "
			if drive["name"]:
				title += "\"%s\" (%s)" % (drive["name"], drive["path"])
			else:
				title += drive["path"]
			
			info = []
			if drive["srobo"]:
				info.append("Robot Memory Stick")

			if drive["last-deployed"]:
				info.append("Last deployed on "+ drive["last-deployed"].strftime("%x @ %X"))
			else:
				info.append("No past deployment")
			
			try:
				logFiles = len([f for f in os.listdir(drive["path"]) if re.match('log.txt', f)])
				if logFiles:
					info.append("%d logs" % logFiles)
			except:
				pass

			messages.append([title, ' - '.join(info)])
			
		def onDriveChosen(x):
			if x < 0:
				pass
			else:
				drive = drives[x]
				theZip = self.makeZip(userPaths[0], pyenvLocation, ignorePatterns)
				target = os.path.join(drive["path"], "robot.zip")
				shutil.copyfile(theZip, target)
				sublime.status_message("Zip deployed successfully to %s!"%target)

		self.window.show_quick_panel(messages, onDriveChosen)


