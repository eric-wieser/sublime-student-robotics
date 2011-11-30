import sublime
import sublime_plugin
import os
import os.path as path
import string
import tempfile
import shutil
import ctypes
import datetime
import zipfile
import time

class DeployZipCommand(sublime_plugin.WindowCommand):
	def setStatus(self, key, status):
		for view in self.window.views():
			view.set_status(key, status)
	def eraseStatus(self, key):
		for view in self.window.views():
			view.erase_status(key)
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

	def getDriveName(self, letter):
		volumeNameBuffer = ctypes.create_unicode_buffer(512)
		fileSystemNameBuffer = ctypes.create_unicode_buffer(512)

		ctypes.windll.kernel32.GetVolumeInformationW(
			ctypes.c_wchar_p(letter),
			volumeNameBuffer, ctypes.sizeof(volumeNameBuffer),
			None, None, None,
			fileSystemNameBuffer, ctypes.sizeof(fileSystemNameBuffer)
		)

		return volumeNameBuffer.value

	def getDrives(self):
		ctypes.windll.kernel32.SetErrorMode(1)
		driveBits = ctypes.windll.kernel32.GetLogicalDrives()
		return [
			{
				"path": letter + ":\\",
				"name": self.getDriveName(letter + ":\\")
			}
			for i, letter in enumerate(string.uppercase)
			if (driveBits >> i) & 1
		]


	def run(self):
		s = sublime.load_settings("Student Robotics.sublime-settings")
		pyenvLocation = path.join(s.get('pyenv-location'), 'pyenv')
		ignorePatterns = s.get('ignore')
		drives = self.getDrives()

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

		sublime.status_message("Exporting from %s..."%userPaths[0])

		def onDriveChosen(x):
			if x < 0:
				pass
			else:
				drive = drives[x]
				theZip = self.makeZip(userPaths[0], pyenvLocation, ignorePatterns)
				target = os.path.join(drive["path"], "robot.zip")
				shutil.copyfile(theZip, target)
				sublime.status_message("Zip deployed successfully to %s!"%target)

		self.window.show_quick_panel([
			[
				"Deploy to " + ("%s (%s)" % (drive["name"], drive["path"]) if drive["name"] else drive["path"]),
				"%s - %s" % (
					drive["srobo"] and "SR Memory Stick" or "Other Device",
					"Last deployed on "+ drive["last-deployed"].strftime("%x @ %X") if drive["last-deployed"] else "No past deployment")
			] for drive in drives
		], onDriveChosen)


