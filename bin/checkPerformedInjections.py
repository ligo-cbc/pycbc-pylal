#!/usr/bin/env python

# This program is used to produce lists of successfully performed hardware injections
# Copyright (C) 2010 John Veitch
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from optparse import OptionParser

from glue.ligolw import ligolw
from glue.ligolw import lsctables
from pylal import SimInspiralUtils
from glue import segments
from glue import segmentdb
from glue.segmentdb import segmentdb_utils

def checkInjection(segments,injection):
	if len(segments)==0: return True
	# Check to see if injection is in all the lists of segments
	res=map(lambda segment:injection.get_end() in segment, segments.values() )
	return reduce(lambda a,b:a and b, res)

usage = """ %prog [options]
Parse a list of scheduled hardware injections, check which were actually performed.
Checks that each injection is performed in all detectors specified (i.e. uses AND).
Ouputs a SimInspiralTable to specified file, or stdout if none is given.
"""

parser=OptionParser(usage)
parser.add_option("-i","--input",action="store",default=None,help="List of scheduled injections",type="string",metavar="INJECTIONS.xml")
parser.add_option("-o","--output",action="store",default=None,help="Output File",type="string",metavar="OUTPUT.xml")
parser.add_option("-H","--H1",action="store_true",default=False,help="Check Hanford 4km")
parser.add_option("-I","--H2",action="store_true",default=False,help="Check Hanford 2km")
parser.add_option("-L","--L1",action="store_true",default=False,help="Check Livingston")
parser.add_option("-V","--V1",action="store_true",default=False,help="Check Virgo")
parser.add_option("-s","--segment-db",metavar="segment_url",default="https://segdb.ligo.caltech.edu",help="URL of segment database")


opts,args=parser.parse_args()

if opts.input==None:
	parser.error("Please specify an input file using --input")

# Read the input file
injections=SimInspiralUtils.ReadSimInspiralFromFiles([opts.input])
injections.sort(key=lambda a:a.get_end())

starttime=injections[0].get_end()
endtime=injections[-1].get_end()
# Fetch list of successful injections from the server
# Returns an LDBD client
segdb_client=segmentdb_utils.setup_database(opts.segment_db)
segdb_engine=segmentdb.query_engine.LdbdQueryEngine(segdb_client)

segments={}
scisegs={}
# Query the database for all the IFOS
for ifo in ['H1','H2','L1','V1']:
	if getattr(opts,ifo):
		if ifo=='V1':
			segname='INJECTION_INSPIRAL'
			scisegname='ITF_SCIENCEMODE'
		else:
			segname='DMT-INJECTION_INSPIRAL'
			scisegname='DMT-SCIENCE'
		segments[ifo]=segmentdb_utils.build_segment_list(segdb_engine,\
				starttime, endtime, ifo, segname)[0]
		scisegs[ifo]=segmentdb_utils.build_segment_list(segdb_engine,\
				starttime,endtime,ifo,scisegname)[0]
		
# Create SimInspiralTable for output
outtable=lsctables.New(lsctables.SimInspiralTable)
# Append the successful injections to the new table
successful=filter(lambda a:checkInjection(segments,a) and checkInjection(scisegs,a), injections)
for inj in successful: outtable.append(inj)

# Create output document
output_doc=ligolw.Document()
# Create LIGO_LW element and append it to the document
output_ligo_lw = ligolw.LIGO_LW()
output_doc.appendChild(output_ligo_lw)
# Add the SimInspiralTable of successful injections
output_doc.childNodes[0].appendChild(outtable)

# Write the output file and finish
if opts.output is not None:
	output_file = open(opts.output,"w")
	output_doc.write(output_file)
	output_file.close()
else:
	output_doc.write()

