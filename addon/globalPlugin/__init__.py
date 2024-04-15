﻿# Código del script clipboard-monitor perteneciente a Héctor Benítez

from nvwave import playWaveFile
from keyboardHandler import KeyboardInputGesture
from threading import Thread
from time import sleep
import gui
import wx
import api
import globalPluginHandler
import speech
import core
import globalVars
root_path= globalVars.appArgs.configPath
import ui
from scriptHandler import script
import os
from .database import *
from .keyFunc import pressKey, releaseKey
from .clipboard_monitor import ClipboardMonitor
import addonHandler

# Lína de traducción
addonHandler.initTranslation()

# Función para romper la cadena de verbalización y callar al sintetizador durante el tiempo especificado
def mute(time, msg= False):
	if msg:
		ui.message(msg)
		sleep(0.1)
	Thread(target=killSpeak, args=(time,), daemon= True).start()

def killSpeak(time):
	if speech.getState().speechMode != speech.SpeechMode.talk: return
	speech.setSpeechMode(speech.SpeechMode.off)
	sleep(time)
	speech.setSpeechMode(speech.SpeechMode.talk)

def disableInSecureMode(decoratedCls):
	if globalVars.appArgs.secure:
		return globalPluginHandler.GlobalPlugin
	return decoratedCls

@disableInSecureMode
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super(GlobalPlugin, self).__init__(*args, **kwargs)
		self.data= []
		self.search_text= None
		self.x= 0
		self.switch= False
		self.monitor= None
		
		if hasattr(globalVars, 'clipboardHistory'):
			self.postStartupHandler()
		core.postNvdaStartup.register(self.postStartupHandler)
		globalVars.clipboardHistory= None

	def postStartupHandler(self):
		Thread(target=self._start, daemon=True).start()

	def _start(self):
		self.monitor= ClipboardMonitor()
		self.monitor.start_monitoring(as_thread=False)

	def getScript(self, gesture):
		if not self.switch: return globalPluginHandler.GlobalPlugin.getScript(self, gesture)
		script= globalPluginHandler.GlobalPlugin.getScript(self, gesture)
		if not script:
			mute(0.3, _('Historial Cerrado'))
			self.finish()
			return
		return globalPluginHandler.GlobalPlugin.getScript(self, gesture)

	def finish(self):
		self.switch= False
		self.clearGestureBindings()

	@script(
		category= 'clipboardHistory',
		# Translators: Descripción del elemento en el diálogo gestos de entrada
		description= _('Activa la capa de comandos. F1 muestra la lista de atajos'),
		gesture= None
	)
	def script_viewData(self, gesture):
		cursor.execute('SELECT string FROM strings ORDER BY id DESC')
		self.data= cursor.fetchall()
		if len(self.data) < 1:
			ui.message(_('Historial vacío'))
			return
		self.switch= True
		self.bindGestures(self.__newGestures)
		ui.message(_('Historial abierto'))

	def script_items(self, gesture):
		key= gesture.mainKeyName
		if key == 'downArrow':
			self.x+=1
			if self.x >= len(self.data):
				self.x= 0
		elif key == 'upArrow':
			self.x-=1
			if self.x < 0:
				self.x= len(self.data)-1
		elif key == 'home':
			self.x= 0
		elif key == 'end':
			self.x= len(self.data)-1
		playWaveFile(os.path.join(dirAddon, "sounds", "click.wav"))
		self.speak()

	def script_copyItem(self, gesture):
		api.copyToClip(self.data[self.x][0])
		ui.message(_('Elemento copiado'))
		self.finish()

	def script_viewItem(self, gesture):
		ui.browseableMessage(self.data[self.x][0], _('Contenido'))
		self.finish()
		mute(0.1, _('Mostrando el contenido'))

	def script_deleteItem(self, gesture):
		cursor.execute('DELETE FROM strings WHERE string=?', (self.data[self.x][0],))
		connect.commit()
		self.data.pop(self.x)
		playWaveFile(os.path.join(dirAddon, "sounds", "delete.wav"))
		if len(self.data) < 1:
			ui.message(_('Lista vacía'))
			self.finish()
			return
		if self.x == len(self.data): self.x-=1
		self.speak()

	def speak(self):
		ui.message(f'{self.x+1}; {self.data[self.x][0]}')

	def script_pasteItem(self, gesture):
		api.copyToClip(self.data[self.x][0])
		self.finish()
		mute(0.2, _('Pegado'))
		pressKey(0x11)
		pressKey(0x56)
		releaseKey(0x56)
		releaseKey(0x11)

	def script_findItem(self, gesture):
		self.finish()
		get_search= wx.TextEntryDialog(
			gui.mainFrame,
			_('Escriba la búsqueda y pulse intro'),
			_('Buscador')
		)
		def callback(result):
			if result == wx.ID_OK:
				self.search_text= get_search.GetValue()
				self.startSearch()
		gui.runScriptModalDialog(get_search, callback)

	def script_searchNextItem(self, gesture):
		self.startSearch()

	def startSearch(self):
		if self.search_text is None:
			ui.message(_('Sin texto de búsqueda'))
			return

		# Intentar encontrar la coincidencia comenzando desde el siguiente elemento
		for i in range(self.x + 1, len(self.data)):
			if self.search_text.lower() in self.data[i][0].lower():
				self.x = i
				mute(0.2, f'{self.x + 1}; {self.data[self.x][0]}')
				self.bindGestures(self.__newGestures)
				return

		# Si no se encuentra, busca desde el comienzo hasta el elemento actual
		for i in range(0, self.x + 1):
			if self.search_text.lower() in self.data[i][0].lower():
				self.x = i
				mute(0.2, f'{self.x + 1}; {self.data[self.x][0]}')
				self.bindGestures(self.__newGestures)
				return

		# Si no se encuentra nada después de buscar todo el rango
		mute(0.2, _('Sin resultados'))
		self.bindGestures(self.__newGestures)

	def script_close(self, gesture):
		mute(0.3, _('Historial cerrado'))
		self.finish()

	def script_historyDelete(self, gesture):
		self.finish()
		wx.CallAfter(self.startHistoryDelete)

	def startHistoryDelete(self):
		modal= wx.MessageDialog(None, _('¿Seguro que quieres eliminar el historial del portapapeles?'), _('Atención'), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
		if modal.ShowModal() == wx.ID_YES:
			cursor.execute('DELETE FROM strings')
			connect.commit()
			speech.cancelSpeech()
			speech.speakMessage(_('Historial eliminado de la base de datos'))
			killSpeak(0.3)

	def script_commandList(self, gesture):
		self.finish()
		string= _('''
Flecha arriba; anterior elemento de la lista
Flecha abajo; siguiente elemento de la lista
Inicio; primer elemento de la lista
Flecha derecha; copia el elemento actual al portapapeles y lo desplaza al comienzo de la lista
Flecha izquierda; abre el contenido del elemento actual en una ventana de NVDA
Retroceso; elimina el actual elemento de la lista
v; Pega el contenido del elemento actual en la ventana con el foco
f; activa la ventana para buscar elementos en la lista
f3; avanza a la siguiente coincidencia  del texto buscado
g; activa la ventana para enfocar el elemento por número de órden
escape; desactiva la capa de comandos
		''')
		ui.browseableMessage(string, _('Lista de comandos'))

	def script_indexSearch(self, gesture):
		self.finish()
		get_search= wx.TextEntryDialog(
			gui.mainFrame,
			_('Escriba el número y pulse intro'),
			_('Hay {} elementos en el historial'.format(len(self.data)))
		)
		def callback(result):
			if result == wx.ID_OK:
				index= get_search.GetValue()
				if index.isdigit() and int(index) > 0 and int(index) <= len(self.data):  # Ajuste aquí
					self.x= int(index)-1
					mute(0.5, f'{index}; {self.data[self.x][0]}')
					self.bindGestures(self.__newGestures)
				else:
					mute(0.3, _('Dato incorrecto o fuera de rango'))
		gui.runScriptModalDialog(get_search, callback)

	def terminate(self):
		if cursor and connect:
			cursor.close()
			connect.close()
			self.monitor.stop_monitoring()

	__newGestures= {'kb:f1': 'commandList',
		'kb:downArrow': 'items',
		'kb:upArrow': 'items',
		'kb:home': 'items',
		'kb:end': 'items',
		'kb:rightArrow': 'copyItem',
		'kb:leftArrow': 'viewItem',
		'kb:backspace': 'deleteItem',
		'kb:v': 'pasteItem',
		'kb:f': 'findItem',
		'kb:f3': 'searchNextItem',
		'kb:g': 'indexSearch',
		'kb:z': 'historyDelete',
		'kb:escape': 'close'}
