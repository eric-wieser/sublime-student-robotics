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
import fnmatch
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
	def makeZipNew(self, userCodePath, zipLocation, ignorePatterns = []):
		self.tmpd = tempfile.mkdtemp(suffix="-sr")
		tempZip = path.join(self.tmpd, "zip")
		shutil.copyfile(zipLocation, tempZip)

		zip = zipfile.ZipFile(tempZip, 'a', zipfile.ZIP_DEFLATED)
		rootlen = len(userCodePath) + 1
		
		for base, dirs, files in os.walk(userCodePath):
			for file in files:
				ignore = False
				for pattern in ignorePatterns:
					ignore = ignore or fnmatch.fnmatch(file, pattern)
				
				if not ignore:
					fn = path.join(base, file)
					zip.write(fn, path.join("user",fn[rootlen:]))
		zip.close()

		return tempZip
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

		def onDriveChosen(x):
			if x < 0:
				pass
			else:
				drive = drives[x]
				theZip = self.makeZipNew(userPaths[0], s.get('prebuilt-zip'), ignorePatterns)#(userPaths[0], pyenvLocation, ignorePatterns)
				target = os.path.join(drive["path"], "robot.zip")
				shutil.copyfile(theZip, target)
				shutil.rmtree(self.tmpd)
				sublime.status_message("Zip deployed successfully to %s!"%target)

		self.window.show_quick_panel([
			[
				"Deploy to " + ("%s (%s)" % (drive["name"], drive["path"]) if drive["name"] else drive["path"]),
				"%s - %s" % (
					drive["srobo"] and "SR Memory Stick" or "Other Device",
					"Last deployed on "+ drive["last-deployed"].strftime("%x @ %X") if drive["last-deployed"] else "No past deployment")
			] for drive in drives
		], onDriveChosen)


