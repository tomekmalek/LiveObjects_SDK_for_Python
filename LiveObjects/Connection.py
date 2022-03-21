#
# Copyright (C) Orange
#
# This software is distributed under the terms and conditions of the 'MIT'
# license which can be found in the file 'LICENSE.md' in this package distribution

import sys
import json
import time

import LiveObjects

INT = "i32"
UINT = "u32"
BINARY = "bin"
STRING = "str"
FLOAT = "f64"
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"

SSL = 8883
NONE = 1883


class LiveObjectsParameter:
    def __init__(self, value, type_, cb=None):
        self.value = value
        self.type = type_
        self.callback = cb


class Connection:
    def __init__(self, debug=True):
        self.__board = LiveObjects.BoardsFactory(net_type=LiveObjects.BoardsInterface.DEFAULT_CARRIER)
        self.mode = self.__board.get_lang_id()

        try:
            if self.mode == LiveObjects.BoardsInterface.PYTHON:
                import paho.mqtt.client as paho
                import os
            elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
                from umqttrobust import MQTTClient
        except ImportError:
            print("[ERROR] U have missing libraries 'Paho-mqtt' (for Python) or 'umqttrobust' (for uPython)")
            sys.exit()

        self.__port = self.__board.get_security_level()
        self.__apiKey = self.__board.get_apikey()
        self.__device_id = self.__board.get_client_id()
        self.__parameters = {}
        self.__server = "mqtt.liveobjects.orange-business.com"
        self.__topic = "dev/data"
        self.__value = "value"
        self.__payload = {self.__value: {}}
        self.__commands = {}
        self.__doLog = debug
        self.quit = False

        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            self.__mqtt = paho.Client(self.__device_id)
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            self.ssl = self.__port == SSL
            self.__mqtt = MQTTClient(self.__device_id, self.__server, self.__port, "json+device",
                                      self.__apiKey, 0, self.ssl, {'server_hostname': self.__server})

    def loop(self):
        if self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            self.__mqtt.check_msg()

    def __onMessage(self, client="", userdata="", msg=""):
        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            if msg.topic == "dev/cfg/upd":
                self.__parameterManager(msg)
            elif msg.topic == "dev/cmd":
                self.__commandManager(msg)
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            if client == b"dev/cfg/upd":
                self.__parameterManager(userdata)
            elif client == b"dev/cmd":
                self.__commandManager(userdata)

    def __onConnect(self, client="", userdata="", flags="", rc=""):
        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            if rc == 0:
                self.outputDebug(INFO, "Connected!")
                if len(self.__commands) > 0:
                    self.outputDebug(INFO, "Subscribing commands")
                    self.__mqtt.subscribe("dev/cmd")
                if len(self.__parameters) > 0:
                    self.outputDebug(INFO, "Subscribing parameters")
                    self.__mqtt.subscribe("dev/cfg/upd")
                    self.__sendConfig()
            else:
                self.outputDebug(ERROR, "Check your api key")
                self.quit=True
                sys.exit()
            #else:
                #self.outputDebug(ERROR,"Unknown error while connecting,quitting...")
                #sys.exit()
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            self.outputDebug(INFO, "Connected, sending config")
            if len(self.__commands) > 0:
                self.outputDebug(INFO, "Subscribing commands")
                self.__mqtt.subscribe(b"dev/cmd")
            if len(self.__parameters) > 0:
                self.outputDebug(INFO, "Subscribing parameters")
                self.__mqtt.subscribe(b"dev/cfg/upd")
                self.__sendConfig()

    def connect(self):
        self.__board.connect()
        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            self.__mqtt.username_pw_set("json+device", self.__apiKey)
            self.__mqtt.on_connect = self.__onConnect
            self.__mqtt.on_message = self.__onMessage
            if self.__port == SSL:
                filename = "/etc/ssl/certs/ca-certificates.crt"

                if self.__board.get_os_id() == LiveObjects.BoardsInterface.WINDOWS:
                    try:
                        import certifi
                        filename = certifi.where()
                    except ImportError:
                        print("[ERROR] U have missing library 'python-certifi-win32'")
                        sys.exit()

                self.__mqtt.tls_set(filename)
            self.__mqtt.connect(self.__server, self.__port, 60)
            self.__mqtt.loop_start()
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            self.__mqtt.set_callback(self.__onMessage)
            self.__mqtt.connect()
            time.sleep(1)
            self.__onConnect()

    def disconnect(self):
        self.__mqtt.disconnect()
        self.outputDebug(INFO, "Disconnected")

    def outputDebug(self, info, *args):
        if self.__doLog:
            print("[", info, "]", end=" ", sep="")
            for arg in args:
                print(arg, end=" ")
            print("")

    def addCommand(self, name, cmd):
        self.__commands[name] = cmd

    def __commandManager(self, msg):
        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            msgDict = json.loads(msg.payload)
            self.outputDebug(INFO, "Received message:\n", json.dumps(msgDict, sort_keys=True, indent=4))
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            msgDict = json.loads(msg)
            self.outputDebug(INFO, "Received message:", json.dumps(msgDict))
        outputMsg = {}
        outputMsg["cid"] = msgDict["cid"]
        response = self.__commands.get(msgDict["req"], self.__default)(msgDict["arg"])
        if len(response) > 0:
            outputMsg["res"] = response
        self.__publishMessage("dev/cmd/res", outputMsg)

    def __default(self, req=""):
        self.outputDebug(INFO, "Command not found!")
        return {"info": "Command not found"}

    def __sendConfig(self):
        outMsg = {"cfg": {}}
        for param in self.__parameters:
            outMsg["cfg"][param] = {"t": self.__parameters[param].type, "v": self.__parameters[param].value}
        self.__publishMessage("dev/cfg", outMsg)

    def __parameterManager(self, msg):
        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            self.outputDebug(INFO, "Received message: ")
            self.outputDebug(INFO, json.loads(msg.payload))
            params = json.loads(msg.payload)
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            self.outputDebug(INFO, "Received message: ")
            self.outputDebug(INFO, json.loads(msg))
            params = json.loads(msg)

        for param in params["cfg"]:
            if params["cfg"][param]["t"] == "i32":
                self.__parameters[param].type = INT
            elif params["cfg"][param]["t"] == "str":
                self.__parameters[param].type = STRING
            elif params["cfg"][param]["t"] == "bin":
                self.__parameters[param].type = BINARY
            elif params["cfg"][param]["t"] == "u32":
                self.__parameters[param].type = UINT
            elif params["cfg"][param]["t"] == "f64":
                self.__parameters[param].type = FLOAT

            self.__parameters[param].value = params["cfg"][param]["v"]
            if self.__parameters[param].callback is not None:
                self.__parameters[param].callback(param, params["cfg"][param]["v"])
        self.__publishMessage("dev/cfg", params)

    def addParameter(self, name, val, type_, cb=None):
        if type_ == INT:
            val = int(val)
        elif type_ == STRING:
            val = str(val)
        elif type_ == BINARY:
            val = bool(val)
        elif type_ == UINT:
            val = int(val)
        elif type_ == FLOAT:
            val = float(val)
        self.__parameters[name] = LiveObjectsParameter(val, type_, cb)

    def getParameter(self, name):
        if self.__parameters[name].type == INT:
            return int(self.__parameters[name].value)
        elif self.__parameters[name].type == STRING:
            return str(self.__parameters[name].value)
        elif self.__parameters[name].type == BINARY:
            return bool(self.__parameters[name].value)
        elif self.__parameters[name].type == UINT:
            return int(self.__parameters[name].value)
        elif self.__parameters[name].type == FLOAT:
            return float(self.__parameters[name].value)
        return 0

    def addToPayload(self, name, val):
        self.__payload[self.__value][name] = val
    
    def setObjectAsPayload(self, val):
        self.__payload[self.__value] = val

    def addModel(self, model):
        self.__payload["model"] = model

    def addTag(self, tag):
        if not "tags" in self.__payload:
            self.__payload["tags"] = []
        self.__payload["tags"].append(tag)

    def addTags(self, tags):
        if not "tags" in self.__payload:
            self.__payload["tags"] = []
        for tag in tags:
            self.__payload["tags"].append(tag)

    def sendData(self):
        if self.quit:
            sys.exit()
        self.__publishMessage("dev/data", self.__payload)
        self.__payload = {}
        self.__payload[self.__value] = {}

    def __publishMessage(self, topic, msg):
        self.outputDebug(INFO, "Publishing message on topic: ", topic)

        if self.mode == LiveObjects.BoardsInterface.PYTHON:
            self.outputDebug(INFO, "\n", json.dumps(msg, sort_keys=True, indent=4))
        elif self.mode == LiveObjects.BoardsInterface.MICROPYTHON:
            self.outputDebug(INFO, json.dumps(msg))

        self.__mqtt.publish(topic, json.dumps(msg))
