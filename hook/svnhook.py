#!/usr/bin/env python
"""Fulltext indexing of committed files.
   
   Copyright 2009 Staffan Olsson repossearch.com

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
   
Requires Solr 1.4-dev example set up as described in:
http://wiki.apache.org/solr/ExtractingRequestHandler
$LastChangedRevision$
"""

'''
The hook is designed to index anything from the repository
history that might be relevant to search for.

Indexing performance is assumed to be of minor importance.
Index size can be reduced by modifying the hook logic, but a
better options is to customize the schema for example by
settings fields to type "ignore".

Comments about the "svnrev" schema are design notes, but
indexing of revision properties and diff is not implemented yet.

The hook consists of three components, kept together in a
single script for ease of inclusion from post-commit hook:
* Repository access
* Handlers for changes
* Solr communication
* Startup from command line

Use rebuild_index.py to reindex a repository from revision 0 to HEAD.
'''

import logging
import logging.handlers
import os
from optparse import OptionParser
from subprocess import Popen
from subprocess import PIPE
import re
from tempfile import NamedTemporaryFile
from urllib import urlencode
import xml.dom.minidom

""" hook options """
parser = OptionParser()
parser.add_option("-p", "--repository", dest="repo",
    help="A local repository path")
parser.add_option("-r", "--revision", dest="rev",
    help="Committed revision")
parser.add_option("", "--nobase", dest="nobase", action='store_true', default=False,
    help="Disable prefixed with repo name (i.e. @base) when indexing. Defaults to %default")
# TODO future --prefix parameter for those who want to index multiple hots or parent paths

parser.add_option("", "--loglevel", dest="loglevel", default="info",
    help="The loglevel (standard Log4J levels, lowercase). Defaults to %default.")
parser.add_option("", "--svnlook", dest="svnlook", default="/usr/bin/svnlook",
    help="The svnlook command, default: %default")
parser.add_option("", "--curl", dest="curl", default="/usr/bin/curl",
    help="The curl command, default: %default")
parser.add_option("", "--solr", dest="solr", default="http://localhost:8080/solr/svnhead/",
    help="Solr host, port and schema. Default: %default")

def getOptions():
    (options, args) = parser.parse_args()
    if options.repo is None:
        print >> sys.stderr, __doc__
        parser.print_help()
        sys.exit(2)
    return options

def optionsPreprocess(options):
    '''
    Derives additional options needed in functions below.
    Raises exception on invalid or missing options.
    '''
    # normalize repository path
    options.repo = options.repo.rstrip("/")
    # derive base from repo path
    if not options.nobase:
        options.base = os.path.basename(options.repo)
    # only numeric revisions supported
    options.rev = long(options.rev)

### ----- hook backend to read from repository ----- ###

def repositoryHistoryReader(options, revisionHandler, pathEntryHandler):
  '''
  Iterates through repository revision and calls the given handlers
  for parse events: new revision and changed path in revision.
  
  This script is called for a single revision so there will only be one
  call to revisionHandler.
  '''
  options.logger.info("Repository '%s' base '%s' rev %d" % (options.repo, options.base, options.rev))
  changedp = Popen([options.svnlook, "changed", "-r %d" % options.rev, options.repo], stdout=PIPE)
  changed = changedp.communicate()[0]
  # assuming utf8 system locale
  changed = changed.decode('utf8')
  # event, revprop support not implemented
  revisionHandler(options, options.rev, dict())

  changematch = re.compile(r"^([ADU_])([U\s])\s+(.+)$")
  for change in changed.splitlines():
    m = changematch.match(change);
    p = "/" + m.group(3)
    pathEntryHandler(options, options.rev, p, m.group(1), m.group(2), not p.endswith('/'))

def repositoryDiff(options, revision, path):
    '''
    Returns diff for revision-1:revision as plaintext for the given path
    '''
    pass

def repositoryGetFile(options, revision, path):
    '''
    Returns contents as NamedTemporaryFile that will be deleted on close()
    '''
    pass

def repositoryGetProplist(options, revision, path):
    '''
    Returns proplist as dictionary with propname:value pairs
    '''
    pass

### ----- event handlers for results from backend ----- ###

def handleRevision(options, revision, revprops):
    '''
    Event handler for new historical revision in repository,
    called in ascending revision number order.
    
    Revision properties should be indexed in svnrev schema at id
    [prefix][base]/[revision number]
    '''
    pass

def handlePathEntry(options, revision, path, action, propaction, isfile):
  '''
  Event handler for changed path in revision.
  Path is unicode with leading slash, trailing slash for folders.
  Action is one of the subversion characters [ADU] or whitespace.
  
  Contents and current property values should be indexed in svnhead
  schema at [prefix][base][path]
  
  Diff for the path at this revision should be indexed in svnrev
  '''
  if not isfile:
    options.logger.debug('Ignoring folder %s' % path)
    return
  options.logger.debug("%s%s  %s" % (action, propaction, path))
  if action == 'D':
    submitDelete(path)
  elif action == 'A':
    submitContents(path)
  elif action == 'U':
    submitContents(path)

def handlePathEntryDelete(options, revision, path):
    '''
    Handles indexing of file deletion.
    '''
    pass

### ----- cummunication with indexing server ----- ###

def curlPathEntryAdd(options, revision, path):
    pass

def curlPathEntryUpdate(optons, revision, path):
    pass

def curlPathEntrySendContents(optons, revision, path):
    pass

def curlPathEntryDelete(options, revision, path):
    pass


### ----- hook start from post-commit arguments ----- ###

def getLogger(options):    
    """ 
    Set up logger based on options 
    and store the instance in options.logger
    """
    LEVELS = {'debug': logging.DEBUG,
              'info': logging.INFO,
              'warning': logging.WARNING,
              'error': logging.ERROR,
              'critical': logging.CRITICAL}
    level = LEVELS.get(options.loglevel)
    if not level:
        raise NameError("Invalid log level %s" % options.loglevel)
    logger = logging.getLogger("Repos Search hook")
    logger.setLevel(level)
    # console
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    options.logger = logger
    
def getProplist(repo, rev, path):
    xml = Popen([options.svnlook, "proplist", "-v", "--xml", "-r %d" % rev, repo, path], stdout=PIPE).communicate()[0]
    return proplistToDict(xml)

def proplistToDict(xmlsource):
    dom = xml.dom.minidom.parseString(xmlsource)
    p = dict()
    for n in dom.getElementsByTagName('property'):
        p[n.getAttribute('name')] = n.firstChild and n.firstChild.nodeValue or ''
    return p

def submitDelete(path):
    options.logger.warn('Delete not implemented. File %s will remain in search index.' % path)

def submitContents(path):
    """path could be a folder so we should handle that"""

    path = path.encode('utf8') # to avoid error from urlencode "UnicodeEncodeError: 'ascii' codec can't encode character u'\xf6' in position 4: ordinal not in range(128)"
    params = {"literal.id": path, 
              "literal.svnrevision": options.rev,
              "commit": "true"}
    # path should begin with slash so that base can be prepended
    # this means that for indexes containing repo name paths do not begin with slash 
    if options.base:
        params["literal.id"] = options.base + params["literal.id"]

    props = getProplist(options.repo, options.rev, path)
    for p in props.keys():
        params['literal.svnprop_' + re.sub(r'[.:]', '_', p)] = props[p].encode('utf8')

    cat = NamedTemporaryFile('wb')
    options.logger.debug("Writing %s to temp %s" % (path, cat.name))    
    catp = Popen([options.svnlook, "cat", "-r %d" % options.rev, options.repo, path], stdout=cat)
    catp.communicate()
    if not catp.returncode is 0:
        options.logger.debug("Cat failed for %s. It must be a folder." % (path))
        return

    # post contents with curl as in solr example
    cat.flush()
    curl = options.curl
    if options.logger.getEffectiveLevel() is logging.DEBUG:
        curl = curl + " -v"
    result = os.system("%s '%supdate/extract?%s' -F 'myfile=@%s'"
              % (curl, options.solr, urlencode(params), cat.name))
    if result:
        raise NameError("Failed to submit document to index, got %d" % result)
    cat.close()
    options.logger.info("Successfully indexed id: %s" % params["literal.id"]);

if __name__ == '__main__':
  options = getOptions()
  getLogger(options)
  optionsPreprocess(options)
  repositoryHistoryReader(options, handleRevision, handlePathEntry)
