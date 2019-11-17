import time
import datetime
from RPi import GPIO

class FlashReader:
  MIN_BYTES = 4
  MAX_BIT_DELAY = 20000 #microseconds

  AWAITING_SYNC = 0
  WATCHING_SYNC = 1
  READING_PREAMBLE = 2
  READING_LENGTH = 3
  READING_DATA = 4


  # typical pin is 25.
  def __init__(self, pin, callback):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    self.callback = callback

    self.last_value = None
    self.last_change = 0

    # Ported from C. Excuse the un-python-ness
    self.calculated_bit_length = None
    self.sync_start = None
    self.zero_time = 0
    self.one_time = 0
    self.zero_count = 0
    self.one_count = 0
    self.zero_length = 0
    self.one_length = 0
    self.preamble_start = None
    self.expected_bytes = 0

    self.bits = []

    self.decoder_state = self.AWAITING_SYNC
    
    def noteChange(channel):
      self.noteChange(channel)
    GPIO.add_event_detect(pin, GPIO.BOTH, callback=noteChange)


  def noteChange(self, channel):
    now = datetime.datetime.now()
    if self.last_value is None:
      self.last_value = GPIO.input(channel) == 0
      self.last_change = now
    else:
      self.last_value = not self.last_value

    self.handleTransition(now, self.last_value)
    self.last_change = now


  def resetSync(self):
    # print "STARTING OVER"
    self.last_value = None
    self.sync_start = None
    self.zero_time = 0
    self.one_time = 0
    self.zero_count = 0
    self.one_count = 0
    self.decoder_state = self.AWAITING_SYNC
    self.expected_bytes = 0
    self.bits = []

  def updateSyncCounts(self, change_delay, value):
    if value:
      self.zero_count += 1;
      self.zero_time += change_delay;
    else:
      self.one_count += 1;
      self.one_time += change_delay;

  def getByte(self, index):
    b = 0
    for i in range(8):
      if self.bits[index*8+i]:
        b |= 1 << (7-i)
    return b

  def printBits(self):
    print "Printing", len(self.bits)/8, "bytes"
    for i in range(0, len(self.bits), 8):
      byte = self.getByte(i/8)
      print i, bin(byte), hex(byte), chr(byte)
    print "Calculated bit length was", self.calculated_bit_length, "-- zero length of", self.zero_length, "-- one length of", self.one_length

  def checkCrc(self):
    # uses Xmodem-CRC, because why not?
    data = [self.getByte(i) for i in range(1, self.expected_bytes-2)]
    crc = 0
    for byte in data:
      crc ^= (byte << 8)
      for i in range(8):
        if crc & 0x8000:
          crc = (crc << 1) ^ 0x1021
        else:
          crc = (crc << 1) & 0xFFFF
    crc &= 0xFFFF
    match = (crc >> 8) == self.getByte(self.expected_bytes-2) and   \
      (crc & 0xFF) == self.getByte(self.expected_bytes-1)

    if not match:
      print "CRC mismatch -- expecting", hex(self.getByte(self.expected_bytes-2)), hex(self.getByte(self.expected_bytes-1)), "but calculated",  hex(crc >> 8), hex(crc &0xFF)
      self.printBits()

    return match

  def handleTransition(self, t, value):
    change_delay = (t - self.last_change).microseconds
    if self.decoder_state is self.AWAITING_SYNC:
      if self.sync_start is None:
        self.sync_start = t
      else:
        if t - self.sync_start <= datetime.timedelta(microseconds=self.MAX_BIT_DELAY * (self.zero_count + self.one_count + 2)):
          self.updateSyncCounts(change_delay, value)
          if self.one_count > 10:
            self.decoder_state = self.WATCHING_SYNC
        else:
          self.resetSync()
      return

    if self.decoder_state is self.WATCHING_SYNC:
      if change_delay < 1.5 * self.MAX_BIT_DELAY:
        self.updateSyncCounts(change_delay, value)
      elif value and change_delay < 3 * self.MAX_BIT_DELAY:
        # preamble has begun!
        self.zero_length = self.zero_time/self.zero_count
        self.one_length = self.one_time/self.one_count
        self.calculated_bit_length = (self.zero_length+self.one_length)/2
        self.preamble_start = self.last_change + datetime.timedelta(microseconds=((self.zero_length / 2)+self.calculated_bit_length))
        self.decoder_state = self.READING_PREAMBLE
        self.bits.append(False)
        self.bits.append(False)
        # preamble starts with two 0s, which don't get read properly below
      else:
        print "LOST SYNC delay", change_delay, "value", value
        self.resetSync()
      return

    if self.decoder_state is self.READING_PREAMBLE:
      if len(self.bits) >= 8:
        if self.getByte(0) == 0x2A:
          self.decoder_state = self.READING_LENGTH
        else:
          print "PREAMBLE FAILED, expected 0x2A 0b00101010, got", bin(self.getByte(0)), hex(self.getByte(0))
          self.resetSync()
          return
  
    if self.decoder_state is self.READING_LENGTH:
      if len(self.bits) >= 16:
        self.expected_bytes = self.getByte(1)+4
        self.decoder_state = self.READING_DATA
  
  
    # else, decoder_state is READING_DATA or we fell through!

    # figure out where the frame is centered
    i = self.last_change + datetime.timedelta(microseconds=(self.zero_length if value else self.one_length) / 2)
  
    while i < t and len(self.bits) < max(self.MIN_BYTES, self.expected_bytes) * 8:
      self.bits.append(not value)
      i += datetime.timedelta(microseconds=self.calculated_bit_length)

    if len(self.bits) >= max(self.MIN_BYTES, self.expected_bytes)*8 or change_delay > self.calculated_bit_length * 16:
      if self.checkCrc():
        self.callback([self.getByte(i) for i in range(2, self.expected_bytes-2)])
      self.resetSync()

if __name__ == '__main__':
  print "Testing FlashRead..."
  br = None
  
  def success(bytes):
    print "Successfully received", len(bytes), "bytes:"
    for index, byte in enumerate(bytes):
      print str(index)+":", bin(byte), hex(byte), "("+chr(byte)+")" if byte >=32 and byte <= 127 else ""
      
  br = FlashReader(25, success)

  while True:
    time.sleep(1)
