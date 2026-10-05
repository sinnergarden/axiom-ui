"""Export only explicitly authorized, previously validated saved UI projections."""
import argparse
from axiom_ui.public_share import export_site

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--selection',required=True,help='Private explicit selection JSON; never Data root/current')
p.add_argument('--output',required=True,help='Public static directory, normally site')
args=p.parse_args()
manifest=export_site(args.selection,args.output)
print('Exported '+str(len(manifest['results']))+' explicitly selected result pages; no business execution.')
