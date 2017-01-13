#! /usr/bin/python3
# Simple script to parse specs and produce CSV files.
# Released by Rusty Russell under CC0: https://creativecommons.org/publicdomain/zero/1.0/

from optparse import OptionParser
import sys
import re
import fileinput

# Figure out if we can determine type from size.
def guess_alignment(message,name,sizestr):

    # Exceptions:
    # - Padding has no alignment requirements.
    # - channel-id is size 8, but has alignment 4.
    # - node_announcement.ipv6 has size 16, but alignment 4 (to align IPv4 addr).
    # - node_announcement.alias is a string, so alignment 1
    # - signatures have no alignment requirement.
    if match.group('name').startswith('pad'):
        return 1

    if match.group('name') == 'channel-id':
        return 4

    if message == 'node_announcement' and match.group('name') == 'ipv6':
        return 4

    if message == 'node_announcement' and match.group('name') == 'alias':
        return 1

    if 'signature' in match.group('name'):
       return 1
    
    # Size can be variable.
    try:
        size = int(match.group('size'))
    except ValueError:
        # If it contains a "*xxx" factor, that's our per-unit size.
        s = re.search('\*([0-9]*)$', match.group('size'))
        if s is None:
            size = 1
        else:
            size = int(s.group(1))

    if size % 8 == 0:
        return 8
    elif size % 4 == 0:
        return 4
    elif size % 2 == 0:
        return 2

    return 1

parser = OptionParser()
parser.add_option("--message-types",
                  action="store_true", dest="output_types", default=False,
                  help="Output MESSAGENAME,VALUE for every message")
parser.add_option("--check-alignment",
                  action="store_true", dest="check_alignment", default=False,
                  help="Check alignment for every member of each message")
parser.add_option("--message-fields",
                  action="store_true", dest="output_fields", default=False,
                  help="Output MESSAGENAME,OFFSET,FIELDNAME,SIZE for every message")

(options, args) = parser.parse_args()

# Example input:
# 1. type: 17 (`MSG_ERROR`)
# 2. data:
#    * [8:channel-id]
#    * [4:len]
#    * [len:data]
message = None
havedata = None
typeline = re.compile('1\. type: (?P<value>[A-Z\|0-9]+) \(`(?P<name>[-A-Za-z_]+)`\)')
dataline = re.compile('\s+\* \[(?P<size>[-a-z0-9*+]+):(?P<name>[-a-z0-9]+)\]')
maskline = re.compile('\* 0x(?P<mask>[0-9]+) \((?P<name>[A-Z]+)\): .*')

masks = {}

def evaluate_masks(masks, typ):
    splits = typ.split('|')
    val = 0
    for s in splits:
        if s in masks:
            val += masks[s]
        else:
            try:
                val += int(s)
            except Exception as e:
                raise ValueError("Unknown mask {name} in type {typ}".format(name=s, typ=typ))
    return val

for i,line in enumerate(fileinput.input(args)):
    line = line.rstrip()
    linenum = i+1

    match = maskline.fullmatch(line)
    if match:
        name, mask, = match.group('name'), match.group('mask')

        if name in masks:
            raise ValueError("Duplicate mask name {name}".format(name))
        else:
            masks[name] = int(mask, 16)
        continue

    match = typeline.fullmatch(line)
    if match:
        if message is not None:
            raise ValueError('{}:Found a message while I was already in a message'.format(linenum))
        message = match.group('name')
        if options.output_types:
            value = match.group('value')
            print("{},{},{}".format(match.group('name'), value, evaluate_masks(masks, value)))
        havedata = None
    elif message is not None and havedata is None:
        if line != '2. data:':
            # This is an empty message type without data
            message = None
            continue
        havedata = True
        dataoff = 0
        off_extraterms = ""
        maxalign = 1
    elif message is not None and havedata is not None:
        match = dataline.fullmatch(line)
        if match:
            align = guess_alignment(message, match.group('name'), match.group('size'))

            if options.check_alignment and dataoff % align != 0:
                raise ValueError('{}:message {} field {} Offset {} not aligned on {} boundary:'.format(linenum, message, match.group('name'), dataoff, align))

            if options.output_fields:
                print("{},{}{},{},{}".format(message,dataoff,off_extraterms,match.group('name'),match.group('size')))

            # Size can be variable.
            try:
                dataoff += int(match.group('size'))
            except ValueError:
                # Offset has variable component.
                off_extraterms = off_extraterms + "+" + match.group('size')
        else:
            message = None
