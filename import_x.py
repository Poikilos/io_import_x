# Blender DirectX importer
# version: see __init__.py

import os
import sys
import re
import struct, binascii
import time

from typing import Union

import bpy
from bpy.types import Armature, EditBone
from bpy_extras import node_shader_utils

import mathutils as bmat
from mathutils import Vector, Matrix

# AttributeError: '_RestrictData' object has no attribute 'filepath':
# myPath = os.path.dirname(bpy.data.filepath)
script_file = os.path.realpath(__file__)
directory = os.path.dirname(script_file)
if not directory in sys.path:
    sys.path.append(directory)

import bel
import bel.mesh
import bel.image
import bel.uv
import bel.material
import bel.ob
import bel.fs

from .templates_x import *

'''
# just a temp hack to reload bel everytime
import imp
imp.reload(bel)
imp.reload(bel.fs)
imp.reload(bel.image)
imp.reload(bel.material)
imp.reload(bel.mesh)
imp.reload(bel.ob)
imp.reload(bel.uv)
'''


###################################################

def load(operator, context, filepath, files,
         global_clamp_size=0.0,
         show_tree=False,
         show_templates=False,
         show_geninfo=False,
         do_not_add_unused_material=False,
         quickmode=False,
         parented=False,
         bone_maxlength=1.0,
         chunksize=False,
         naming_method=0,
         use_ngons=True,
         use_edges=True,
         use_smooth_groups=True,
         use_split_objects=True,
         use_split_groups=True,
         use_groups_as_vgroups=False,
         use_image_search=True,
         lefthanded=True,
         global_matrix: Matrix = None,
         ):
    if quickmode:
        parented = False

    bone_minlength = bone_maxlength / 100.0

    # global templates, tokens
    rootTokens = []
    namelookup = {}
    imgnamelookup = {}
    chunksize = int(chunksize)
    reserved_type = (
        'dword',
        'float',
        'string'
    )

    '''
        'array',
        'Matrix4x4',
        'Vector',
    '''
    '''
    with * : defined in dXdata

    WORD     16 bits
    * DWORD     32 bits
    * FLOAT     IEEE float
    DOUBLE     64 bits
    CHAR     8 bits
    UCHAR     8 bits
    BYTE     8 bits
    * STRING     NULL-terminated string
    CSTRING     Formatted C-string (currently unsupported)
    UNICODE     UNICODE string (currently unsupported)

BINARY FORMAT
# TOKENS in little-endian WORDs
#define TOKEN_NAME         1
#define TOKEN_STRING       2
#define TOKEN_INTEGER      3
#define TOKEN_GUID         5
#define TOKEN_INTEGER_LIST 6
#define TOKEN_FLOAT_LIST   7
#define TOKEN_OBRACE      10
#define TOKEN_CBRACE      11
#define TOKEN_OPAREN      12
#define TOKEN_CPAREN      13
#define TOKEN_OBRACKET    14
#define TOKEN_CBRACKET    15
#define TOKEN_OANGLE      16
#define TOKEN_CANGLE      17
#define TOKEN_DOT         18
#define TOKEN_COMMA       19
#define TOKEN_SEMICOLON   20
#define TOKEN_TEMPLATE    31
#define TOKEN_WORD        40
#define TOKEN_DWORD       41
#define TOKEN_FLOAT       42
#define TOKEN_DOUBLE      43
#define TOKEN_CHAR        44
#define TOKEN_UCHAR       45
#define TOKEN_SWORD       46
#define TOKEN_SDWORD      47
#define TOKEN_VOID        48
#define TOKEN_LPSTR       49
#define TOKEN_UNICODE     50
#define TOKEN_CSTRING     51
#define TOKEN_ARRAY       52

    '''

    # COMMON REGEX
    space = '[\ \t]{1,}'  # at least one space / tab
    space0 = '[\ \t]{0,}'  # zero or more space / tab

    # DIRECTX REGEX TOKENS
    r_template = r'template' + space + '[\w]*' + space0 + '\{'
    if quickmode:
        r_sectionname = r'Mesh' + space + '[\W-]*'
    else:
        r_sectionname = r'[\w]*' + space + '[\w-]*' + space0 + '\{'
    r_refsectionname = r'\{' + space0 + '[\w-]*' + space0 + '\}'
    r_endsection = r'\{|\}'

    # dX comments
    r_ignore = r'#|//'

    # r_frame = r'Frame' + space + '[\w]*'
    # r_matrix = r'FrameTransformMatrix' + space + '\{[\s\d.,-]*'
    # r_mesh = r'Mesh' + space + '[\W]*'

    ###################
    ## STEP 1 FUNCTIONS
    ###################

    ## HEADER
    # returns header values or False if directx reco tag is missing
    # assuming there's never comment header and that xof if the 1st
    # string of the file
    '''
     they look like xof 0303txt 0032
     4       Magic Number (required) "xof "
     2       Minor Version 03
     2       Major Version 02
     4       Format Type (required)
        "txt " Text File
        "bin " Binary File
        "tzip" MSZip Compressed Text File
        "bzip" MSZip Compressed Binary File
     4       Float Accuracy "0032" 32 bit or "0064" 64 bit
    '''

    def dXheader(data):
        l = data.read(4)
        if l != b'xof ':
            print('no header found !')
            data.seek(0)
            return False
        minor = data.read(2).decode()
        major = data.read(2).decode()
        format = data.read(4).decode().strip()
        accuracy = int(data.read(4).decode())
        data.seek(0)
        return (minor, major, format, accuracy)

    ##
    def dXtree(data, quickmode=False):
        tokens = {}
        templates = {}
        tokentypes = {}
        c = 0
        lvl = 0
        tree = ['']
        ptr = 0
        eol = 0
        trunkated = False
        previouslvl = False
        while True:
            # for l in data.readlines() :
            lines, trunkated = nextFileChunk(data, trunkated)
            if lines == None: break
            for l in lines:

                # compute pointer position
                ptr += eol
                c += 1
                eol = len(l) + 1
                # print(c,data.tell(),ptr+eol)
                # if l != '' : print('***',l)
                # if l == ''  : break
                l = l.strip()

                # remove blank and comment lines
                if l == '' or re.match(r_ignore, l):
                    continue

                # one line token cases level switch
                if previouslvl:
                    lvl -= 1
                    previouslvl = False

                # print('%s lines in %.2f\''%(c,time.clock()-t),end='\r')
                # print(c,len(l)+1,ptr,data.tell())
                if '{' in l:
                    lvl += 1
                    if '}' in l: previouslvl = True  # ; print('got one line token : \n%s'%l)
                elif '}' in l:
                    lvl -= 1
                # print(c,lvl,tree)

                if quickmode == False:
                    ## look for templates
                    if re.match(r_template, l):
                        tname = l.split(' ')[1]
                        templates[tname] = {'pointer': ptr, 'line': c}
                        continue

                    ## look for {references}
                    if re.match(r_refsectionname, l):
                        refname = namelookup[l[1:-1].strip()]
                        # print('FOUND reference to %s in %s at line %s (level %s)'%(refname,tree[lvl-1],c,lvl))
                        # tree = tree[0:lvl]
                        parent = tree[lvl - 1]
                        # tag it as a reference, since it's not exactly a child.
                        # put it in childs since order can matter in sub tokens declaration
                        tokens[parent]['childs'].append('*' + refname)
                        if refname not in tokens:
                            print('reference to %s done before its declaration (line %s)\ncreated dummy' % (refname, c))
                            tokens[refname] = {}
                        if 'user' not in tokens[refname]:
                            tokens[refname]['users'] = [parent]
                        else:
                            tokens[refname]['users'].append(parent)
                        continue

                ## look for any token or only Mesh token in quickmode
                if re.match(r_sectionname, l):
                    tokenname = getName(l, tokens)
                    # print('FOUND %s %s %s %s'%(tokenname,c,lvl,tree))
                    # print('pointer %s %s'%(data.tell(),ptr))
                    if lvl == 1: rootTokens.append(tokenname)
                    typ = l.split(' ')[0].strip().lower()
                    tree = tree[0:lvl]
                    if typ not in tokentypes:
                        tokentypes[typ] = [tokenname]
                    else:
                        tokentypes[typ].append(tokenname)
                    parent = tree[-1]
                    if tokenname in tokens:
                        tokens[tokenname]['pointer'] = ptr
                        tokens[tokenname]['line'] = c
                        tokens[tokenname]['parent'] = parent
                        tokens[tokenname]['childs'] = []
                        tokens[tokenname]['type'] = typ

                    else:
                        tokens[tokenname] = {'pointer': ptr,
                                             'line': c,
                                             'parent': parent,
                                             'childs': [],
                                             'users': [],
                                             'type': typ
                                             }
                    tree.append(tokenname)
                    if lvl > 1 and quickmode == False:
                        tokens[parent]['childs'].append(tokenname)

        return tokens, templates, tokentypes

    ## returns file binary chunks
    def nextFileChunk(data, trunkated=False, chunksize=1024):
        if chunksize == 0:
            chunk = data.read()
        else:
            chunk = data.read(chunksize)
        if format == 'txt':
            lines = chunk.decode('utf-8', errors='ignore')
            # if stream : return lines.replace('\r','').replace('\n','')
            lines = lines.replace('\r', '\n').split('\n')
            if trunkated: lines[0] = trunkated + lines[0]
            if len(lines) == 1:
                if lines[0] == '': return None, None
                return lines, False
            return lines, lines.pop()
        # wip, todo for binaries
        else:
            print(chunk)
            for word in range(0, len(chunk)):
                w = chunk[word:word + 4]
                print(word, w, struct.unpack("<l", w), binascii.unhexlify(w))

    # name unnamed tokens, watchout for x duplicate
    # for blender, referenced token in x should be named and unique..
    def getName(line: str, tokens) -> str:
        xnam = line.split(' ')[1].strip()

        # if xnam[0] == '{' : xnam = ''
        if xnam and xnam[-1] == '{': xnam = xnam[:-1]

        name = xnam
        if len(name) == 0: name = line.split(' ')[0].strip()

        namelookup[xnam] = bel.bpyname(name, tokens, suffix=4)

        return namelookup[xnam]

    ###################
    ## STEP 2 FUNCTIONS
    ###################
    # once the internal dict is populated the functions below can be used

    ## from a list of tokens, displays every child, users and references
    '''
      walk_dxtree( [ 'Mesh01', 'Mesh02' ] ) # for particular pieces
      walk_dxtree(tokens.keys()) for the whole tree
    '''

    def walk_dXtree(field, lvl=0, tab=''):
        for fi, tokenname in enumerate(field):
            if lvl > 0 or tokens[tokenname]['parent'] == '':
                if tokenname not in tokens:
                    tokenname = tokenname[1:]
                    ref = 'ref: '
                else:
                    ref = False

                frame_type = tokens[tokenname]['type']
                line = ('{:7}'.format(tokens[tokenname]['line']))
                log = ' %s%s (%s)' % (ref if ref else '', tokenname, frame_type)
                print('%s.%s%s' % (line, tab, log))
                if fi == len(field) - 1: tab = tab[:-3] + '   '

                if ref == False:
                    for user in tokens[tokenname]['users']:
                        print('%s.%s |__ user: %s' % (line, tab.replace('_', ' '), user))
                    walk_dXtree(tokens[tokenname]['childs'], lvl + 1, tab.replace('_', ' ') + ' |__')

                if fi == len(field) - 1 and len(tokens[tokenname]['childs']) == 0:
                    print('%s.%s' % (line, tab))

    ## remove eol, comments, spaces from a raw block of datas
    def cleanBlock(block):
        while '//' in block:
            s = block.index('//')
            e = block.index('\n', s + 1)
            block = block[0:s] + block[e:]
        while '#' in block:
            s = block.index('#')
            e = block.index('\n', s + 1)
            block = block[0:s] + block[e:]
        block = block.replace('\n', '').replace(' ', '').replace('\t ', '')
        return block

    def readToken(tokenname):
        token = tokens[tokenname]
        datatype = token['type'].lower()
        if datatype in templates:
            tpl = templates[datatype]
        elif datatype in defaultTemplates:
            tpl = defaultTemplates[datatype]
        else:
            print("can't find any template to read %s (type : %s)" % (tokenname, datatype))
            return False
        # print('> use template %s'%datatype)
        block = readBlock(data, token)
        ptr = 0
        # return dXtemplateData(tpl,block)
        fields, ptr = dXtemplateData(tpl, block)
        if datatype in templatesConvert:
            fields = eval(templatesConvert[datatype])

        return fields

    def dXtemplateData(tpl, block, ptr=0):
        # print('dxTPL',block[ptr])
        pack = []
        for member in tpl['members']:
            # print(member)
            dataname = member[-1]
            datatype = member[0].lower()
            if datatype == 'array':
                datatype = member[1].lower()
                s = dataname.index('[') + 1
                e = dataname.index(']')
                # print(dataname[s:e])
                length = eval(dataname[s:e])
                # print("array %s type %s length defined by '%s' : %s"%(dataname[:s-1],datatype,dataname[s:e],length))
                dataname = dataname[:s - 1]
                datavalue, ptr = dXarray(block, datatype, length, ptr)
                # print('back to %s'%(dataname))
            else:
                length = 1
                datavalue, ptr = dXdata(block, datatype, length, ptr)

            # if len(str(datavalue)) > 50 : dispvalue = str(datavalue[0:25]) + ' [...] ' + str(datavalue[-25:])
            # else : dispvalue = str(datavalue)
            # print('%s :  %s %s'%(dataname,dispvalue,type(datavalue)))
            exec('%s = datavalue' % (dataname))
            pack.append(datavalue)
        return pack, ptr + 1

    def dXdata(block, datatype, length, s=0, eof=';'):
        # print('dxDTA',block[s])
        # at last, the data we need
        # should be a ';' but one meet ',' often, like in meshface
        if datatype == 'dword':
            e = block.index(';', s + 1)
            try:
                field = int(block[s:e])
            except:
                e = block.index(',', s + 1)
                field = int(block[s:e])
            return field, e + 1
        elif datatype == 'float':
            e = block.index(eof, s + 1)
            return float(block[s:e]), e + 1
        elif datatype == 'string':
            e = block.index(eof, s + 1)
            return str(block[s + 1:e - 1]), e + 1
        else:
            if datatype in templates:
                tpl = templates[datatype]
            elif datatype in defaultTemplates:
                tpl = defaultTemplates[datatype]
            else:
                print("can't find any template for type : %s" % (datatype))
                return False
            # print('> use template %s'%datatype)
            fields, ptr = dXtemplateData(tpl, block, s)
            if datatype in templatesConvert:
                fields = eval(templatesConvert[datatype])
            return fields, ptr

    def dXarray(block, datatype, length, s=0):
        # print('dxARR',block[s])
        lst = []
        if datatype in reserved_type:
            eoi = ','
            for i in range(length):
                if i + 1 == length: eoi = ';'
                datavalue, s = dXdata(block, datatype, 1, s, eoi)
                lst.append(datavalue)

        else:
            eoi = ';,'
            for i in range(length):
                if i + 1 == length: eoi = ';;'
                # print(eoi)
                e = block.index(eoi, s)
                # except : print(block,s) ; popo()
                datavalue, na = dXdata(block[s:e + 1], datatype, 1)
                lst.append(datavalue)
                s = e + 2
        return lst, s

    ###################################################

    ## populate a template with its datas
    # this make them available in the internal dict. should be used in step 2 for unknown data type at least
    def readTemplate(data, tpl_name, display=False):
        ptr = templates[tpl_name]['pointer']
        line = templates[tpl_name]['line']
        # print('> %s at line %s (chr %s)'%(tpl_name,line,ptr))
        data.seek(ptr)
        block = ''
        trunkated = False
        go = True
        while go:
            lines, trunkated = nextFileChunk(data, trunkated, chunksize)  # stream ?
            if lines == None:
                break
            for l in lines:
                # l = data.readline().decode().strip()
                block += l.strip()
                if '}' in l:
                    go = False
                    break

        uuid = re.search(r'<.+>', block).group()
        templates[tpl_name]['uuid'] = uuid.lower()
        templates[tpl_name]['members'] = []
        templates[tpl_name]['restriction'] = 'closed'

        members = re.search(r'>.+', block).group()[1:-1].split(';')
        for member in members:
            if member == '': continue
            if member[0] == '[':
                templates[tpl_name]['restriction'] = member
                continue
            templates[tpl_name]['members'].append(member.split(' '))

        if display:
            print('\ntemplate %s :' % tpl_name)
            for k, v in templates[tpl_name].items():
                if k != 'members':
                    print('  %s : %s' % (k, v))
                else:
                    for member in v:
                        print('  %s' % str(member)[1:-1].replace(',', ' ').replace("'", ''))

            if tpl_name in defaultTemplates:
                defaultTemplates[tpl_name]['line'] = templates[tpl_name]['line']
                defaultTemplates[tpl_name]['pointer'] = templates[tpl_name]['pointer']
                if defaultTemplates[tpl_name] != templates[tpl_name]:
                    print('! DIFFERS FROM BUILTIN TEMPLATE :')
                    print('raw template %s :' % tpl_name)
                    print(templates[tpl_name])
                    print('raw default template %s :' % tpl_name)
                    print(defaultTemplates[tpl_name])
                    # for k,v in defaultTemplates[tpl_name].items() :
                    #    if k != 'members' :
                    #        print('  %s : %s'%(k,v))
                    #    else :
                    #        for member in v :
                    #            print('  %s'%str(member)[1:-1].replace(',',' ').replace("'",''))
                else:
                    print('MATCHES BUILTIN TEMPLATE')

    ##  read any kind of token data block
    # by default the block is cleaned from inline comment space etc to allow data parsing
    # useclean = False (retrieve all bytes) if you need to compute a file byte pointer
    # to mimic the file.tell() function and use it with file.seek()
    def readBlock(data, token, clean=True):
        ptr = token['pointer']
        data.seek(ptr)
        block = ''
        # lvl = 0
        trunkated = False
        go = True
        while go:
            lines, trunkated = nextFileChunk(data, trunkated, chunksize)
            if lines == None: break
            for l in lines:
                # eol = len(l) + 1
                l = l.strip()
                # c += 1
                block += l + '\n'
                if re.match(r_endsection, l):
                    go = False
                    break
        s = block.index('{') + 1
        e = block.index('}')
        block = block[s:e]
        if clean: block = cleanBlock(block)
        return block

    def getChilds(tokenname):
        childs = []
        # '*' in childname means it's a reference. always perform this test
        # when using the childs field
        for childname in tokens[tokenname]['childs']:
            if childname[0] == '*': childname = childname[1:]
            childs.append(childname)
        return childs

    def fixupTransformMatrix( matrix: Matrix ) -> Matrix:
        '''
            Converts from a D3DX matrix format to Blender's Matrix format.
            Returns a transposed copy of the given matrix. If lefthanded, then inverts its Z-axis as well.
        '''

        # !!! DirectX stores translation in 4th row, not 4th column, so a transpose is needed.
        m = matrix.transposed()

        if lefthanded:
            # Change from left-handed to right-handed.
            zinv = Matrix()
            zinv[2][2] = -1.0
            m = zinv @ m @ zinv

        return m

    def fixupTranslation( vec: list ):
        '''
            If lefthanded, this inverts the Z-axis of the given translation.
            Returns the given translation structure.
        '''

        if lefthanded:
            vec[2] *= -1.0

        return vec

    def fixupUV( uv: list ):
        '''
            Inverts the V component.
            Returns the given uv structure.
        '''

        uv[1] = 1.0 - uv[1]

        return uv

    # the input nested list of [bonename, matrix, [child0,child1..]] is given by import_dXtree()
    def buildArm( armdata: Union[ str, Armature ], child, lvl=0, parent_matrix: Matrix = None ) -> Union[ Armature, EditBone ]:

        bonename, bonemat, bonechilds = child

        if lvl == 0:
            armname = armdata
            armdata = bpy.data.armatures.new(name=armname)
            arm = bpy.data.objects.new(armname, armdata)

            view_layer = bpy.context.view_layer
            collection = view_layer.active_layer_collection.collection
            collection.objects.link(arm)
            arm.select_set( True )
            view_layer.objects.active = arm

            bpy.ops.object.mode_set(mode='EDIT')
            parent_matrix = Matrix()

        bone: EditBone = armdata.edit_bones.new(name=bonename)
        bonematW = parent_matrix @ bonemat

        bone.head = bonematW.to_translation()

        # bone.roll.. ?
        # bone.head = parent_matrix.to_translation()
        # bone.tail = bonematW.to_translation()

        bone_length = bone_maxlength
        last_bone_head: Vector = None
        for bonechild in bonechilds:
            bonechild = buildArm(armdata, bonechild, lvl=lvl + 1, parent_matrix=bonematW)
            bonechild.parent = bone

            last_bone_head = bonechild.head
            bone_length = min((last_bone_head - bone.head).length, bone_length)

        if len( bonechilds ) == 1:
            bone.tail = Vector( last_bone_head )
        else:
            bone.tail = ( bonematW @ Matrix.Translation( (bone_length, 0, 0) ) ).to_translation()

        if lvl == 0:
            bpy.ops.object.mode_set(mode='OBJECT')
            return arm
        return bone

    def import_dXtree(field, file: str, lvl=0):
        tab = ' ' * lvl * 2
        if field == []:
            if show_geninfo: print('%s>> no childs, return False' % (tab))
            return False
        ob = False
        mat = False
        is_root = False
        frames = []
        obs = []

        parentname = tokens[field[0]]['parent']
        if show_geninfo: print('%s>>childs in frame %s :' % (tab, parentname))

        for tokenname in field:

            tokentype = tokens[tokenname]['type']

            # frames can contain more than one mesh
            if tokentype == 'mesh':
                # object and mesh naming :
                # if parent frame has several meshes : obname = meshname = mesh token name,
                # if parent frame has only one mesh  : obname = parent frame name, meshname =  mesh token name.
                if parentname:
                    meshcount = 0
                    for child in getChilds(parentname):
                        if tokens[child]['type'] == 'mesh':
                            meshcount += 1
                            if meshcount == 2:
                                parentname = tokenname
                                break
                else:
                    parentname = tokenname

                ob = getMesh(parentname, tokenname, debug=show_geninfo)
                ob.name = file
                obs.append(ob)

                if show_geninfo: print('%smesh : %s' % (tab, tokenname))

            # frames contain one matrix (empty or bone)
            elif tokentype == 'frametransformmatrix':
                [mat] = readToken(tokenname)

                if show_geninfo: print('%smatrix : %s' % (tab, tokenname), mat)

            # frames can contain 0 or more frames
            elif tokentype == 'frame':
                frames.append(tokenname)
                if show_geninfo: print('%sframe : %s' % (tab, tokenname))

        if mat: mat = fixupTransformMatrix( mat )

        # matrix is used for mesh transform if some mesh(es) exist(s)
        if ob:
            is_root = True
            if not mat:
                mat = fixupTransformMatrix( Matrix() )
                operator.report( {'WARNING'}, 'No transform was defined in Frame %s, assuming identity transform.' % parentname )

            if parentname == '':
                mat @= global_matrix
            if len(obs) == 1:
                ob.matrix_world = mat
            else:
                ob = bel.ob.new(parentname, None, naming_method)
                ob.matrix_world = mat
                for child in obs:
                    child.parent = ob

        # matrix only, store it as a list as we don't know if
        # it's a bone or an empty yet
        elif mat:
            ob = [parentname, mat, []]

        # nothing case ?
        else:
            ob = [parentname, Matrix() @ global_matrix, []]
            if show_geninfo: print('%snothing here' % (tab))

        childs = []

        for tokenname in frames:
            if show_geninfo: print('%s<Begin %s :' % (tab, tokenname))

            # child is either False, empty, object, or a list or undefined name matrices hierarchy
            child = import_dXtree(getChilds(tokenname), file, lvl=lvl + 1)
            if child and type(child) != list:
                is_root = True
            childs.append([tokenname, child])
            if show_geninfo: print('%sEnd %s>' % (tab, tokenname))

        if is_root and parentname != '':

            if show_geninfo: print('%send of tree a this point' % (tab))
            if type(ob) == list:
                mat = ob[1]
                ob = bel.ob.new(parentname, None, naming_method)
            ob.matrix_world = mat

        for tokenname, child in childs:
            if show_geninfo: print('%sbegin2 %s>' % (tab, tokenname))
            # returned a list of object(s) or matrice(s)
            if child:

                # current frame is an object or an empty, we parent this frame to it
                # if eot or (ob and ( type(ob.data) == type(None) or type(ob.data) == bpy.types.Mesh ) ) :
                if is_root:
                    # this branch is an armature, convert it
                    if type(child) == list:
                        if show_geninfo: print('%sconvert to armature %s' % (tab, tokenname))
                        child = buildArm(tokenname, child)

                    # parent the obj/empty/arm to current
                    # or apply the global user defined matrix to the object root
                    if parentname != '':
                        child.parent = ob
                    else:
                        child.matrix_world = global_matrix

                # returned a list of parented matrices. append it in childs list
                elif type(child[0]) == str:
                    ob[2].append(child)

                # child is an empty or a mesh, so current frame is an empty, not an armature
                elif ob and (type(child.data) == type(None) or type(child.data) == bpy.types.Mesh):
                    # print('  child data type: %s'%type(child.data))
                    child.parent = ob
                    # print('%s parented to %s'%(child.name,ob.name))

            # returned False
            else:
                if show_geninfo: print('%sreturned %s, nothing' % (tab, child))

        # print('>> %s return %s'%(field,ob))
        return ob  # if ob else False

    # build from mesh token type
    def getMesh(obname: str, tokenname: str, debug=False) -> bpy.types.Object:

        if debug: print('\nmesh name : %s' % tokenname)

        verts = []
        edges = []
        faces = []
        matslots = []
        facemats = []
        uvs = []
        groupnames = []
        groupindices = []
        groupweights = []

        nVerts, verts, nFaces, faces = readToken(tokenname)

        for vec in verts:
            fixupTranslation( vec )
        
        if debug: print('verts    : %s %s\nfaces    : %s %s' % (nVerts, len(verts), nFaces, len(faces)))

        for childname in getChilds(tokenname):

            tokentype = tokens[childname]['type']

            # UV
            if tokentype == 'meshtexturecoords':
                uv = readToken(childname)

                for _uv in uv: fixupUV( _uv )

                uv = bel.uv.asFlatList(uv, faces)
                
                uvs.append(uv)

                if debug: print('uv       : %s' % (len(uv)))

            # MATERIALS
            elif tokentype == 'meshmateriallist':

                nbslots, facemats = readToken(childname)

                if debug: print('facemats : %s' % (len(facemats)))

                # Register the Materials mapped in this Mesh.
                # Only Material children are allowed in a MeshMaterialList.
                for slot_index, mat_token in enumerate(getChilds(childname)):

                    (face_color, alpha), power, specCol, emitCol = readToken( mat_token )

                    # Find texture file reference, if any.
                    texture_ref = None
                    normal_texture_path = None
                    for texture_token in getChilds(mat_token):
                        [_texture_ref] = readToken(texture_token)
                        if _texture_ref and len(_texture_ref) > 0:
                            texture_ref = _texture_ref

                    if texture_ref is not None:
                        # Search for normals file (that name of texture file with postfix "_normal")
                        f = texture_ref.rsplit(".", 1)
                        f.insert(-1, "_normal")
                        norm_file = "".join(f[0:len(f) - 1])
                        for ext in ["jpg", "jpeg", "png", "bmp"]:
                            nrm = norm_file + "." + ext
                            if os.path.exists(path + "/" + nrm):
                                normal_texture_path = path + "/" + nrm
                                break

                    # Register the material.
                    mat = bpy.data.materials.new( 'dXnoname' if texture_ref is None else texture_ref )
                    mat.use_nodes = True
                    mat_wrap = node_shader_utils.PrincipledBSDFWrapper(mat, is_readonly=False)

                    mat.blend_method = 'BLEND' if alpha < 1.0 else 'OPAQUE'
                    mat_wrap.base_color = face_color
                    mat_wrap.alpha = alpha
                    mat_wrap.specular = power
                    mat.specular_color = specCol

                    # Load the base texture of the Material, if it exists.
                    if texture_ref is not None:
                        texture_path = path + "/" + texture_ref
                        img = bpy.data.images.load( texture_path, check_existing=True ) if os.path.exists( texture_path ) else None
                        if img is not None:
                            mat_wrap.base_color_texture.image = img
                        
                    # Load the normal map texture of the Material, if it exists.
                    if normal_texture_path is not None:
                        img = bpy.data.images.load( normal_texture_path, check_existing=True ) if os.path.exists( normal_texture_path ) else None
                        if img is not None:
                            mat_wrap.normalmap_texture.image = img
                    
                    matslots.append( mat.name ) # use name property to ensure correct name in Blender
                    
                if debug: print('matslots : %s' % matslots)

            # VERTICES GROUPS/WEIGHTS
            elif tokentype == 'skinweights':
                groupname, nverts, vindices, vweights, mat = readToken(childname)

                mat = fixupTransformMatrix( mat )

                if groupname in namelookup:
                    groupname = namelookup[groupname]
                    if debug:
                        print('vgroup    : %s (%s/%s verts) %s' % (
                            groupname, len(vindices), len(vweights), 'bone' if groupname in tokens else ''))

                    # if debug : print('matrix : %s\n%s'%(type(mat),mat))

                    groupnames.append(groupname)
                    groupindices.append(vindices)
                    groupweights.append(vweights)

                else:
                    operator.report( {'WARNING'}, 'Encountered undefined vertex group %s! Skipping.' % groupname )

        ob = bel.mesh.write(obname, tokenname,
            verts, edges, faces,
            matslots, facemats, uvs,
            groupnames, groupindices, groupweights,
            use_smooth_groups,
            naming_method)

        # Fixup the Mesh's normals.
        ob.data.flip_normals()

        return ob

    ## here we go

    x_file_dir = os.path.dirname(filepath)

    for item_file in files:
        item_file_path = (os.path.join(x_file_dir, item_file.name))

        print('\nimporting %s...' % item_file.name)
        start = time.clock()
        path = os.path.dirname(item_file_path)
        item_file_path = os.fsencode(item_file_path)
        with open(item_file_path, 'rb') as data:
            header = dXheader(data)

            if global_matrix is None:
                global_matrix = Matrix()

            if header:
                minor, major, format, accuracy = header

                if show_geninfo:
                    print('\n%s directX header' % item_file.name)
                    print('  minor  : %s' % (minor))
                    print('  major  : %s' % (major))
                    print('  format : %s' % (format))
                    print('  floats are %s bits' % (accuracy))

                if format in ['txt']:  # , 'bin' ] :

                    ## FILE READ : STEP 1 : STRUCTURE
                    if show_geninfo: print('\nBuilding internal .x tree')
                    t = time.clock()
                    tokens, templates, tokentypes = dXtree(data, quickmode)
                    readstruct_time = time.clock() - t
                    if show_geninfo: print('built tree in %.2f\'' % (readstruct_time))  # ,end='\r')

                    ## populate templates with datas
                    for tplname in templates:
                        readTemplate(data, tplname, show_templates)

                    ## DATA TREE CHECK
                    if show_tree:
                        print('\nDirectX Data Tree :\n')
                        walk_dXtree(tokens.keys())

                    ## DATA IMPORTATION
                    if show_geninfo:
                        # print(tokens)
                        print('Root frames :\n %s' % rootTokens)
                    if parented:
                        import_dXtree(rootTokens, item_file.name)
                    else:
                        for tokenname in tokentypes['mesh']:
                            obname = tokens[tokenname]['parent']
                            # object and mesh naming :
                            # if parent frame has several meshes : obname = meshname = mesh token name,
                            # if parent frame has only one mesh  : obname = parent frame name, meshname =  mesh token name.
                            if obname:
                                meshcount = 0
                                for child in getChilds(obname):
                                    if tokens[child]['type'] == 'mesh':
                                        meshcount += 1
                                        if meshcount == 2:
                                            obname = tokenname
                                            break
                            else:
                                obname = tokenname

                            ob = getMesh(obname, tokenname, debug=show_geninfo)
                            ob.matrix_world = global_matrix

                    print('done in %.2f\'' % (time.clock() - start))  # ,end='\r')

                else:
                    print('only .x files in text format are currently supported')
                    print('please share your file to make the importer evolve')
        rootTokens = []

    return {'FINISHED'}
