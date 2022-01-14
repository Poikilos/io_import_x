# io_import_x
(based on directX_blender by littleneo)
Import .x files into Blender. The **Poikilos fork** attempts to maintain compatibility with the latest stable Blender and allows install via GUI (See "Install" in readme).

## Primary Goals

* Import anything from an .x file
  (obviously verts and faces but also uv, armatures, weights, normals).
* Import .x in binary format [not yet implemented]

Known Issues:
Tasks left undone are complex, so pull requests will probably be the only way to resolve them.
- Bones or models may not be reoriented from y-up to z-up and other similar issues such as bones rotated incorrectly may occur where the x file differs from Blender geometry. Since one file may differ from another, how to deal with this consistently is unknown.
- Animations aren't imported. The bones would have to be imported correctly (see issue above) first. Then, pose frames would have to be added to the bones (accounting for whether bones have parents which would make animations relative). Importing a keyframe on every frame may be the only way (but good enough--you can always remove some manually to improve the animation).

-littleneo and Poikilos


## License
This project is distributed under the GNU General Public License v3 (see
LICENSE file). Although the original repo did not have a license file,
the plugin is also at Blender's [svn](https://svn.blender.org/svnroot/bf-extensions/contrib/py/scripts/addons/io_directx_bel/)
and [git](https://git.blender.org/gitweb/gitweb.cgi/blender-addons-contrib.git/tree/refs/heads/blender2.7:/io_directx_bel)
repos, and therefore under the [GPL](https://git.blender.org/gitweb/gitweb.cgi/blender.git/tree/HEAD:/doc/license)
as required by Blender Foundation for all add-ons. Any public licensed
code cannot later be limited to a more restrictive license, so adding a
GPLv3 license to this repo is ok.


## Install
- Above (on the [io_import_x page GitHub](https://github.com/poikilos/io_import_x)), click "Code", "Download ZIP."
1. Start Blender
2. Download & *Save* zip from GitHub. If you click open you may not be
   able to find the zip later _(you must use the poikilos fork or
   accepted git commits in order for this method to work, otherwise copy
   the extracted io_directx_bel folder to
   ~/.config/blender/2.79/scripts/addons/ on GNU+Linux systems or
   %APPDATA%/Blender Foundation/blender/2.79/scripts/addons)_ on Windows
   and skip to step 3)
   * Click "File," "User Preferences," "Add-ons"
   * Click "Install..." (In earlier Blender versions, "Install add-on from file...")
   * Choose the downloaded io_import_x-master.zip (usually in your
     "Downloads" directory)
3. Enable the add-on in the "Add-ons" tab of "User Preferences".
4. The preference to enable the add-on saves automatically by default
   unless using an older version of Blender. If auto-save preferences is
   not enabled, click "Save User Preferences" to keep the add-on
   enabled for other scenes.

-Poikilos


## Usage
* File > Import > DirectX


## Planned Features
* Export to .x or mod/co-maintain the existing x exporter.
* This project is also a prototype for a 'Blender Exchange Layer'
  project. BEL would be a common layer logically located between an
  importer/exporter addon and the blender data format, that would
  provide a common set of...:
  * methods to retrieve/inject objects in Blender
  * transformation and selection tools between an import/export script
    and Blender (rotate, rescale, filter, etc.)
  * parsing helpers for new io addons
* PLY won't be used unfortunately (it's way too slow as far as I tested)
-littleneo and Poikilos
[See also TODO below]


## Changes
see CHANGELOG.md


## Developer Notes
* I don't want to load the whole file into memory as it can be huge, so
  the importer processes the file in chunks.
* I want random access to 3D data to import pieces, not always
  everything:
  1. Preprocess entire file, retrieving tokens and building an empty
     internal dict with only pointers, no 3D data.
  2. Call any token by name and retrieve the 3D data thanks to pointers
     stored in dicts.
-littleneo and Poikilos

### TODO
* Between step 1 and 2 above, a UI should be provided to select,
  transform, or otherwise process before import.
* I need to know the pointer position of tokens but data.tell() is slow
  a += pointer computed from line length is way faster. To deal with
  EOL (end of line), use rb (read binary) mode; `readline()` is ok in
  binary mode 'rb' with \r\n (win) \n (unix) but not \r mac.
  - Reads 2 characters for windows
  - Reads 1 character if file was produced on mac/Linux
  - On Linux, a Windows EOL (\r\n) becomes \n\n (adding an extra line)
  - On Mac, the \r in a Windows EOL becomes \n so line numbering and
    data read is wrong.
  - Catching this in binary mode allows support for bad newlines (mixed
    \r and \r\n)
  - For now it only works for text format, but the functions called will
    be independent of the container type.

-littleneo and Poikilos

### File Format Parsing

#### Read Main Structure

##### Read Main Token Names
(any 'template', any 'frame', any 'mesh')
* store names in a token directory:
  * token['template'] for templates:
    ```
token['template'][templatename]
token['template'][templatename]['pointer']          (int) chr position in .x file (tell() like*)
token['template'][templatename]['line']             (int) line number in .x file
```
  * token['frame'] for frame and mesh type:
    ```
token['template'][frame or mesh name]
token['template'][frame or mesh name]['pointer']    (int) chr position in .x file (tell() like*)
token['template'][frame or mesh name]['line']       (int) line number in .x file
token['template'][frame or mesh name]['type']       (str) 'ob/bone' or 'mesh'
token['template'][frame or mesh name]['parent']     (str) frame parent of current item
token['template'][frame or mesh name]['childs']     (str list) list of child frame or mesh names
token['template'][frame or mesh name]['matrix']     (int) for now chr position of FrameTransformMatrix
```

At the end of main structure, the script prints a tree of the data.

#### Read Template Definitions

For each template in the dict, populate definitions in it.
Create new fields in each token['template'][templatename]
according to values found in .x:
```
token['template'][templatename]['uuid']                 (str) <universally unique identifier>
token['template'][templatename]['members']['name']      (str) member name
token['template'][templatename]['members']['type']      (str) DWORD,FLOAT etc keywords or template name
token['template'][templatename]['restriction']          (str) 'open' , 'closed' , or the specidied (restricted) value
```

### Optimization
Allow 2 steps: preprocess, then random access to file:
* First, preprocess the file quickly. Only retrieve main info--nothing
  about verts, faces etc info like number of mats, textures,
  objects/mesh/bone trees: 150000 lines in 5 secs
* Allow user to select what to import.
* Retrieve selected data, using the 'pointer' value to seek() to the
  needed data, then grab/parse/translate into something usable.
* Templates are used at this point to know how to parse individual parts
  (the parser is adaptive).

So far this looks fast (tested on windows).
Preprocessing can be important because of eol and the code I wrote to
compute pointer value.
* (data.tell() is slow)
* Only one .x file tested, header is: xof 0303txt 0032 (windows \r\n eol)
* I don't know a lot about .x format:
  * **uuid** :
    are the member/restriction always the same for a same uuid/template ?
    template name can vary for a same uuid ?
  * **syntax** :
    blank lines IN a stream of a {} section, after ; ?
    comments // and # IN a stream of data ?
    '{' and '<something>' and '}' on the same line or '{' '}' are always unique ?
-littleneo


## Credits
* TEST FILES:
  <http://assimp.svn.sourceforge.net/viewvc/assimp/trunk/test/models/X/>


## References
* <http://paulbourke.net/dataformats/directx/>
* <http://www.informikon.com/various/the-simplest-skeletal-animation-possible.html>
* <http://msdn.microsoft.com/en-us/library/windows/desktop/bb173011%28v=VS.85%29.aspx>
* <http://www.toymaker.info/Games/index.html>


## Discussions
* <https://blender.community/c/rightclickselect/kYcbbc/>
* <https://www.reddit.com/r/blender/comments/beq3al/importing_x_files_directx_is_almost_working_help/>
* <https://stackoverflow.com/questions/5767634/import-directx-x-into-blender#comment98211206_16675435>
* <https://blender.stackexchange.com/questions/107834/blender-2-79a-x-files>
* <https://github.com/littleneo/directX_blender/issues/6>
* <https://github.com/limemidolin/directX_blender/pull/1/commits>


## See also
* A fault-tolerant x loader in Irrlicht:
  <https://sourceforge.net/p/irrlicht/code/HEAD/tree/trunk/source/Irrlicht/CXMeshFileLoader.cpp#l740>
* The downstream version in the Blender repository
  <https://svn.blender.org/svnroot/bf-extensions/contrib/py/scripts/addons/io_directx_bel/__init__.py>
  is missing fixes from the <2013 littleneo version, so I mentioned that
  as a comment to my Right-Click Select post at the link under
  "Discussions" above. Also, they seemed to have done a search and
  replace do update certain things for Blender 2.8 but it is not working
  in either 2.79b or 2.80 (nightly 2018-04-18).
