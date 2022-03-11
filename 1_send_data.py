#
# Copyright (C) Orange
#
# This software is distributed under the terms and conditions of the 'MIT'
# license which can be found in the file 'LICENSE.md' in this package distribution

import time
import LiveObjects

board = LiveObjects.BoardsFactory(net_type=LiveObjects.BoardsInterface.DEFAULT_CARRIER)

apikey = board.get_apikey()
client_id = board.get_client_id()
security_level = board.get_security_level()

# Create LiveObjects with parameters:  Board - ClientID - Security - APIKEY
lo = LiveObjects.Connection(board, client_id, security_level, apikey)

MESSAGE_RATE = 5

# Main program
board.network_connect()
lo.connect()		# Connect to LiveObjects
last = uptime = time.time()

while True:
	if (time.time()) >= last + MESSAGE_RATE:
		lo.addToPayload("uptime", int(time.time() - uptime))		# Add value to payload: name - value
		lo.sendData()												# Sending data to cloud
		last = time.time()
		lo.loop() 						# Check for incoming messages and if connection is still active
