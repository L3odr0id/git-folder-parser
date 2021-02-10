"""
Folder parser .git
"""
import collections
import zlib
import os
import argparse

# The only non - "stock" library in this project is graphviz
# used exclusively to reduce the number of lines in the code
from graphviz import Digraph


class GitTree:
    """
    Object Tree class
    """
    type = b'tree'

    def __init__(self, data, c):
        self.items = GitTree.tree_parse(data)
        self.my_hash = c
        self.trees = []  # list of subtrees
        self.blobs = []  # list of blobs

    @staticmethod
    def get_actual_data(raw, start=0):
        """
        Get data from a tree file
        """
        # find first space
        x = raw.find(b' ', start)

        # Read the mode of working with the file
        mode = raw[start:x]

        # Find the end of the "file path"
        y = raw.find(b'\x00', x)
        # read the file path
        path = raw[x + 1:y]

        # Read hash
        sha = hex(
            int.from_bytes(
                raw[y + 1:y + 21], "big"))[2:]
        return y + 21, GitTreeLeaf(mode, path, sha)

    @staticmethod
    def tree_parse(raw):
        """
        Parse tree
        """
        pos = 0
        max = len(raw)
        ret = list()
        while pos < max:
            pos, data = GitTree.get_actual_data(raw, pos)
            ret.append(data)

        return ret


class GitCommit:
    """
    Commit class
    """
    type = b'commit'

    def __init__(self, data, c):
        self.data = GitCommit.data_parse(data)
        self.my_hash = c
        self.tree = None

    def set_tree(self, tree: GitTree):
        """
        Set a tree for a commit
        """
        self.tree = tree

    @staticmethod
    def data_parse(raw, start=0, dct=None):
        """
        Function for parsing information from a commit
        :param raw: data
        :param start: cursor position, where we start reading from
        :param dct: the dictionary where the data is written
        """
        if not dct:
            dct = collections.OrderedDict()

        # we are looking for the next place where in theory there can be useful data
        spc = raw.find(b' ', start)
        nl = raw.find(b'\n', start)

        # if the transition to a new line is earlier than the nearest space or
        # spaces are missing, then the remaining data is a commit message
        if (spc < 0) or (nl < spc):
            dct[b''] = raw[start + 1:]
            return dct

        # read the key for the following data
        key = raw[start:spc]

        # find the end of the value whose key we read
        end = start
        while True:
            end = raw.find(b'\n', end + 1)
            if raw[end + 1] != ord(' '):
                break

        # write variable
        value = raw[spc + 1:end].replace(b'\n ', b'\n')

        # checking not to overwrite the data for the key,
        # a add new ones
        if key in dct:
            if type(dct[key]) == list:
                dct[key].append(value)
            else:
                dct[key] = [dct[key], value]
        else:
            dct[key] = value

        return GitCommit.data_parse(raw, start=end + 1, dct=dct)


class GitBlob:
    """
    Blob class
    """
    type = b'blob'

    def __init__(self, data, c):
        self.blobData = data
        self.my_hash = c


class GitTreeLeaf(object):
    """
    Class of tree elements.
    In the instances of the class, we write the information that
    we read from the files in the folder .git/objects.

    And the instances of GitBlob, GitTree, and GitCommit contain data
    that we parsed and analyzed.
    """
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha


class Reader:
    """
    A class that reads data from .git/objects
    """
    def __init__(self, path: str):
        self.objects = []
        try:
            os.chdir(path + '/.git/objects')
            self.read_objects_folder()
        except FileNotFoundError:
            print('Can not find .git in '+path)

    def read_objects_folder(self):
        """
        Read all the files inside .git/objects
        (except for some)
        """
        dirs = [name for name in os.listdir(".") if os.path.isdir(name)]
        dirs.remove('pack')
        dirs.remove('info')
        # print(dirs)

        for i in dirs:
            # print('reading in '+i)
            os.chdir(i)
            a = Reader.read_objects(i)
            if isinstance(a, list):
                for j in a:
                    self.objects.append(j)
            else:
                self.objects.append(a)
            os.chdir('..')

    @staticmethod
    def read_objects(s: str):
        """
        Read the files inside the folder and parse them
        """
        files = [name for name in os.listdir(".")]
        res = []
        # print(files)
        for i in files:
            with open(i, "rb") as f:
                raw = zlib.decompress(f.read())

                # Understand what kind of object it is
                x = raw.find(b' ')
                fmt = raw[0:x]

                # Skip Null terminator
                y = raw.find(b'\x00', x)

                # Create the desired object
                if fmt == b'tree':
                    c = GitTree
                elif fmt == b'blob':
                    c = GitBlob
                elif fmt == b'commit':
                    c = GitCommit
                else:
                    c = None

                if c:
                    res.append(c(raw[y + 1:], s + i))
        return res


class DependenciesResolver:
    """
    A class that, by hash, restores the hierarchy of objects
    """
    def __init__(self, objects: list):
        self.commits = []
        self.trees = []
        self.blobs = []
        self.set_commits_trees_blobs(objects)
        self.set_trees()

    def set_commits_trees_blobs(self, objects: list):
        """
        Sort all of the objects on the commits, trees and blobs
        """
        for i in objects:
            if isinstance(i, GitCommit):
                self.commits.append(i)
            if isinstance(i, GitTree):
                self.trees.append(i)
            if isinstance(i, GitBlob):
                self.blobs.append(i)

    def set_trees(self):
        """
        Recursively install the dependencies between the trees and blobs
        """
        for i in self.commits:
            h = i.data[b'tree']
            i.set_tree(self.__get_tree(h))

        for i in self.trees:
            for j in i.items:
                b = bytes(j.sha, 'utf-8')
                tmp = self.__get_tree(b)
                if tmp is None:
                    tmp = self.__get_blob(b)
                    if tmp is not None:
                        i.blobs.append(tmp)
                else:
                    i.trees.append(tmp)

    def __get_tree(self, h: bytes):
        """
        Get a tree by hash
        """
        for i in self.trees:
            if h.decode("utf-8") == i.my_hash:
                return i

    def __get_blob(self, h: bytes):
        """
        Get a blob by hash
        """
        for i in self.blobs:
            if h.decode("utf-8") == i.my_hash:
                return i


class MakeGraph:
    """
    The class that draws the graph
    """
    def __init__(self, d: DependenciesResolver):
        self.resolver = d
        self.graph = Digraph(comment='Monster git parser', format='svg', strict=True)
        self.make_basic_nodes()
        self.parse_deps()

    def make_basic_nodes(self):
        """
        Create beautiful nodes for commits
        """
        self.graph.attr('node', shape='square', color='gold1', style='filled')
        for commit in self.resolver.commits:
            commit_msg = commit.data[b''].decode('utf-8')
            commit_sha = commit.my_hash
            self.graph.node(commit_sha, commit_msg)

    def parse_tree(self, tree: GitTree, parent: str, path: str):
        """
        Recursively add trees and blobs to the graph
        """
        self.graph.attr('node', shape='doublecircle')
        self.graph.node(tree.my_hash, path)
        self.graph.edge(parent, tree.my_hash)
        for item in tree.items:
            # if object is file
            if item.mode == b'100644':
                path = item.path.decode('utf-8')
                if MakeGraph.need_to_draw(path):
                    i_hash = item.sha
                    cur_item = i_hash + path
                    self.graph.attr('node', shape='circle')
                    self.graph.node(cur_item, path)
                    self.graph.edge(tree.my_hash, cur_item)
                    blob = ''
                    for i in tree.blobs:
                        if i.my_hash == item.sha:
                            blob = i
                            break

                    # match the file to its contents
                    if isinstance(blob, GitBlob) and blob.blobData.decode("utf-8") != '':
                        self.graph.attr('node', shape='egg')
                        # we will output only the first 20 characters of the file to the diagram
                        self.graph.node(blob.my_hash, blob.blobData.decode("utf-8")[:20])
                        self.graph.edge(cur_item, blob.my_hash)

            # if object is tree
            if item.mode == b'40000':
                local_tree = None
                for i in tree.trees:
                    if i.my_hash == item.sha:
                        local_tree = i
                        break
                if local_tree:
                    self.parse_tree(local_tree, tree.my_hash, item.path.decode('utf-8'))

    def parse_deps(self):
        """
        Install dependencies for commits and start drawing the graph for trees
        """
        self.graph.attr('node', color='black', style="")
        for commit in self.resolver.commits:
            commit_msg = commit.data[b''].decode('utf-8')
            commit_sha = commit.my_hash
            tree = commit.tree
            if b'parent' in commit.data.keys():
                if isinstance(commit.data[b'parent'], list):
                    for j in commit.data[b'parent']:
                        parent = self.get_commit_by_sha(j.decode('utf-8'))
                        if parent:
                            self.graph.edge(parent.my_hash, commit_sha)
                else:
                    parent = self.get_commit_by_sha(commit.data[b'parent'].decode('utf-8'))
                    if parent:
                        self.graph.edge(parent.my_hash, commit_sha)

            self.parse_tree(tree, commit_sha, commit_msg + '`s tree')

    def get_commit_by_sha(self, sha: str):
        """
        Find a commit by hash
        """
        for i in self.resolver.commits:
            if i.my_hash == sha:
                return i

    @staticmethod
    def need_to_draw(name: str):
        """
        Do we need to draw the file on the diagram?
        """
        l = ['.txt', '.java', '.cpp', '.html', '.js']
        for i in l:
            if i in name:
                return True
        return False


def get_arguments():
	"""
	Parse arguments from cmd
	"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--path", dest="path", help="Enter path to .git folder")
    parser.add_argument('--no-input', dest='no_console', action='store_false')
    options = parser.parse_args()
    return options


if __name__ == '__main__':

    # get path to .git from args
    path = get_arguments().path
    if path is None and get_arguments().no_console:
        path = str(input("Enter path to .git folder:"))
    elif path is None:
        path = '.'

    absolutePath = os.path.abspath('')

    # read the objects and return to the initial folder
    a = Reader(path)
    os.chdir(absolutePath)

    # identify the dependencies, and draw the graph
    if len(a.objects) > 0:
        b = DependenciesResolver(a.objects)
        m = MakeGraph(b)

        # output a text representation to the console and render the image
        print(m.graph.source)
        m.graph.render()
