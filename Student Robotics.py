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
import json

WINDOWS = os.name == 'nt'
if WINDOWS:
	import ctypes

PLUGIN_DIRECTORY = os.getcwd()

class Drive(object):
	@staticmethod
	def getNameFromPath(path):
		if WINDOWS:
			fileSystemNameBuffer = ctypes.create_unicode_buffer(512)
			volumeNameBuffer = ctypes.create_unicode_buffer(512)

			ctypes.windll.kernel32.GetVolumeInformationW(
				ctypes.c_wchar_p(path),
				volumeNameBuffer, ctypes.sizeof(volumeNameBuffer),
				None, None, None,
				fileSystemNameBuffer, ctypes.sizeof(fileSystemNameBuffer)
			)

			return volumeNameBuffer.value

	@classmethod
	def getDrives(cls, skip = []):
		if WINDOWS:
			ctypes.windll.kernel32.SetErrorMode(1)
			driveBits = ctypes.windll.kernel32.GetLogicalDrives()
			return [
				cls(letter + ':\\')
				for i, letter in enumerate(string.uppercase)
				if letter not in skip and (driveBits >> i) & 1
			]
		else:
			return [
				cls(path.join('/media', name))
				for name in os.listdir('/media')
			]


	def __init__(self, path, name = None):
		self.path = path
		self.name = name or Drive.getNameFromPath(path)
	
	def __str__(self):
		if self.name:
			return '\'%s\' (%s)' % (self.name, self.path)
		else:
			return self.path

	def __repr__(self):
		if self.name:
			return '%s(path=%s, name=%s)' % (self.__class__.__name__, repr(self.path), repr(self.name))
		else:
			return '%s(%s)' % (self.__class__.__name__, repr(self.path))
	
class RobotDrive(Drive):
	def __init__(self, *args, **kargs):
		Drive.__init__(self, *args, **kargs)
		
		self.srobo = path.exists(path.join(self.path, '.srobo'))

		self.zipPath = path.join(self.path, 'robot.zip')
		try:
			self.lastDeployed = datetime.datetime.fromtimestamp(path.getmtime(self.zipPath))
		except:
			self.lastDeployed = None

		self.logs = glob.glob(path.join(self.path, 'log*')) + glob.glob(path.join(self.path, 'old-logs', 'log*'))
	
	@classmethod
	def getDrives(cls, skip = []):
		drives = super(RobotDrive, cls).getDrives(skip)
		drives.sort(key = lambda d: d.srobo, reverse = True)
		return drives

class DeployZipCommand(sublime_plugin.WindowCommand):
	"""
	A command that finds the user code, and deploy `robot.zip` to a drive
	selected by the user
	"""

	def __init__(self, *args, **kwargs):
		self.tmpd = None
		self.settings = None
		sublime_plugin.WindowCommand.__init__(self, *args, **kwargs)

	def is_enabled(self):
		return bool(self.getProjectFolders())

	def makeZip(self, userCodePath):
		"""
		Build a SR zip from the specified user code, by copying the code into
		a pre-configured zip stored in the plugin folder, and store it in a
		temporary directory. This zip should be updated regularly
		"""

		#Transform globs to regular expressions
		ignoreGlobs = self.settings.get('ignore')
		ignoreRegex = re.compile(r'|'.join(map(fnmatch.translate, ignoreGlobs)) or r'$.')

		rootlen = len(userCodePath) + 1

		#Make a temporary folder
		self.tmpd = tempfile.mkdtemp(suffix='-sr')

		#Copy the premade zip into it
		zipPath = path.join(self.tmpd, 'zip')
		shutil.copyfile(path.join(PLUGIN_DIRECTORY, 'robot.zip'), zipPath)

		#Open the zip for modification
		zip = zipfile.ZipFile(zipPath, 'a', zipfile.ZIP_DEFLATED)

		for root, dirs, files in os.walk(userCodePath):
			# exclude files and dirs - colon syntax actually modifies the array
			dirs[:] = [d for d in dirs if not ignoreRegex.match(d)]
			files = [f for f in files if not ignoreRegex.match(f)]

			#Make full paths

			for fname in (os.path.join(root, f) for f in files):
				zip.write(fname, path.join('user', fname[rootlen:]))
		zip.close()

		return zipPath

	def showDriveList(self, drives, callback):
		"""Present the user with a choice of the drives available"""
		messages = []
		for drive in drives:			
			title = 'Deploy to %s' % drive
			
			info = []
			if drive.srobo:
				info.append('Robot Memory Stick')

			if drive.lastDeployed:
				info.append('Last deployed on '+ drive.lastDeployed.strftime('%x @ %X'))
			else:
				info.append('No past deployment')
			
			if drive.logs:
				info.append('%d logs' % len(drive.logs))

			messages.append([title, ' - '.join(info)])

		self.window.show_quick_panel(messages, lambda x: callback(drives[x]) if x >= 0 else None)

	def getProjectFolders(self):
		"""Find potential SR code locations"""
		return [
			folder
			for folder in self.window.folders()
			if path.exists(path.join(folder, '.git')) and path.exists(path.join(folder, 'robot.py'))
		]

	def onDriveChosen(self, drive, target):
		theZip = self.makeZip(target)
		shutil.copyfile(theZip, drive.zipPath)
		shutil.rmtree(self.tmpd)
		sublime.status_message('Zip deployed successfully to %s!' % drive.zipPath)


	def run(self):
		self.settings = sublime.load_settings('Student Robotics.sublime-settings')

		#Find drives
		drives = RobotDrive.getDrives(self.settings.get('ignore-drives'))
		if not drives:
			sublime.error_message('Is the USB stick plugged in?')
			return

		#Find potential code locations
		userPaths = self.getProjectFolders()
		if not userPaths:
			sublime.error_message('You need to open your project folder in the folder view')
			return
		
		sublime.status_message('Exporting from %s...'%userPaths[0])

		self.showDriveList(drives, lambda d: self.onDriveChosen(d, userPaths[0]))

class DeployCurrentFileCommand(DeployZipCommand):
	def is_enabled(self):
		self.start()
		return DeployZipCommand.is_enabled(self)

	def start(self):
		"""Load the current file when run, or checking if runnable"""
		self.currentFile = self.window.active_view().file_name()

	def getProjectFolders(self):
		allFolders = DeployZipCommand.getProjectFolders(self)
		return [folder for folder in allFolders if self.currentFile.startswith(folder)]

	def onDriveChosen(self, drive, target):
		configPath = os.path.join(target, 'config.json')
		config = {}
		try:
			with open(configPath, 'r') as f:
				config = json.load(f)
		except:
			sublime.status_message('config.json not found - creating new file')

		
		config["execute"] = '.'.join(self.currentFile[len(target)+1:-3].split('\\'))

		with open(configPath, 'w') as f:
			json.dump(config, f, indent=4)

		DeployZipCommand.onDriveChosen(self, drive, target)

	def run(self):
		self.start()
		DeployZipCommand.run(self)


class ShowLogCommand(sublime_plugin.WindowCommand):
	LOG_HEADING_WIDTH = 80
	"""
	A command that shows the Student Robotics logs from a given flash drive
	"""
	def _output_to_view(self, output_file, output, clear=False):
		edit = output_file.begin_edit()
		if clear:
			region = sublime.Region(0, self.output_view.size())
			output_file.erase(edit, region)
		output_file.insert(edit, 0, output)
		output_file.end_edit(edit)

	def scratch(self, output, title=False, **kwargs):
		scratch_file = self.window.new_file()
		if title:
			scratch_file.set_name(title)
		scratch_file.set_scratch(True)
		self._output_to_view(scratch_file, output, **kwargs)
		scratch_file.set_read_only(True)
		return scratch_file


	def run(self):

		#load settings, get drives
		s = sublime.load_settings('Student Robotics.sublime-settings')
		drives = RobotDrive.getDrives(s.get('ignore-drives'))

		#filter out logless drives
		drives = [drive for drive in drives if drive.logs]

		#build the array of messages for the quickpanel
		messages = [
			[drive.path, '%d log files' % len(drive.logs)]
			for drive in drives
		]

		def showLogs(x):
			if x >= 0:
				drive = drives[x]

				logs = []

				for f in drive.logs:
					timestamp = path.getmtime(f)
					dateString = datetime.datetime.fromtimestamp(timestamp).strftime('%x @ %X')

					heading = ''.join([
						a if a != " " else b
						for a, b in zip(
							f.ljust(self.LOG_HEADING_WIDTH),
							dateString.rjust(self.LOG_HEADING_WIDTH)
						)
					])

					log = open(f)
					logs.append(
						heading +  '\n' +
						'=' * self.LOG_HEADING_WIDTH + '\n' +
						log.read()
					)

				self.scratch('\n\n'.join(logs), title = 'SR Logs')

		#Only give a choice if there is more than one option
		if len(messages) > 1:
			self.window.show_quick_panel(messages, showLogs)
		elif messages:
			showLogs(0)
		else:
			sublime.error_message('No log files found')
