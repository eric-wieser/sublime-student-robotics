import os
import sublime
import sublime_plugin
import os.path as path
import string
import tempfile
import shutil
import datetime
import zipfile
import fnmatch
import re
import glob

WINDOWS = os.name == 'nt'
if WINDOWS:
	import ctypes

PLUGIN_DIRECTORY = os.getcwd()

#Apparently needed. We'll see.
#.replace(os.path.normpath(os.path.join(os.getcwd(), '..', '..')) + os.path.sep, '').replace(os.path.sep, '/')


def getDrives(self, skip = []):
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
			if letter not in skip and (driveBits >> i) & 1 #hack for network
		]
	else:
		return [
			{
				"path": path.join('/media', name),
				"name": None
			}
			for name in os.listdir('/media')
		]
def getRobotDrives(ignore):
#Sort out drives
	drives = getDrives(ignore)

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

	return drives

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

	def makeZipNew(self, userCodePath, ignorePatterns = []):
		#Transform ignorePatterns (globs) to regular expressions
		ignore = re.compile(r'|'.join(map(fnmatch.translate, ignorePatterns)) or r'$.')
		rootlen = len(userCodePath) + 1

		#Make a temporary folder
		self.tmpd = tempfile.mkdtemp(suffix="-sr")

		#Copy the premade zip into it
		zipPath = path.join(self.tmpd, "zip")
		shutil.copyfile(path.join(PLUGIN_DIRECTORY, 'robot.zip'), zipPath)

		#Open the zip for modification
		zip = zipfile.ZipFile(zipPath, 'a', zipfile.ZIP_DEFLATED)

		for root, dirs, files in os.walk(userCodePath):
			# exclude files and dirs - colon syntax actually modifies the array
			dirs[:] = [d for d in dirs if not ignore.match(d)]
			files = [f for f in files if not ignore.match(f)]

			#Make full paths

			for fname in (os.path.join(root, f) for f in files):
				zip.write(fname, path.join("user", fname[rootlen:]))
		zip.close()

		return zipPath

	

	def run(self):
		s = sublime.load_settings("Student Robotics.sublime-settings")
		ignorePatterns = s.get('ignore')

		drives = getRobotDrives(s.get('ignore-drives'))
		#Find potential code locations
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
			if x >= 0:
				drive = drives[x]
				theZip = self.makeZipNew(
					userPaths[0],
					ignorePatterns
				)
				target = os.path.join(drive["path"], "robot.zip")
				shutil.copyfile(theZip, target)
				shutil.rmtree(self.tmpd)
				sublime.status_message("Zip deployed successfully to %s!" % target)
		self.window.show_quick_panel(messages, onDriveChosen)

class ShowLogCommand(sublime_plugin.WindowCommand):

	def get_window(self):
		return self.window
	 
	def _output_to_view(self, output_file, output, clear=False):
			edit = output_file.begin_edit()
			if clear:
				region = sublime.Region(0, self.output_view.size())
				output_file.erase(edit, region)
			output_file.insert(edit, 0, output)
			output_file.end_edit(edit)

	def scratch(self, output, title=False, **kwargs):
		scratch_file = self.get_window().new_file()
		if title:
			scratch_file.set_name(title)
		scratch_file.set_scratch(True)
		self._output_to_view(scratch_file, output, **kwargs)
		scratch_file.set_read_only(True)
		return scratch_file


	def run(self):
		s = sublime.load_settings("Student Robotics.sublime-settings")
		drives = getRobotDrives(s.get('ignore-drives'))
		messages = []

		for drive in drives:
			drive["logs"] = glob.glob(path.join(drive["path"], 'log.*'))
			if drive["logs"]:
				messages.append([
					drive["path"],
					"%d log files" % len(drive["logs"])
				])

		def f(x):
			if x >= 0:
				drive = drives[x]

				logs = []

				for f in drive["logs"]:
					modified = datetime.datetime.fromtimestamp(path.getmtime(f))
					log = open(f)
					logs.append(
						modified.strftime("%x @ %X") +
						'  ' +
						f + '\n' +
						'=' * 80 + '\n' +
						log.read()
					)
				self.scratch('\n\n'.join(logs), title = "log")
			else:
				sublime.status_message("No log files!")
		self.window.show_quick_panel(messages, f)