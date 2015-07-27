#!/usr/bin/python

__author__ = 'mmin18'

from subprocess import Popen, PIPE, check_call
import sys
import os
import re

def is_gradle_project(dir):
    return os.path.isfile(os.path.join(dir, 'build.gradle'))

def parse_properties(path):
    return os.path.isfile(path) and dict(line.strip().split('=') for line in open(path) if ('=' in line and not line.startswith('#'))) or {}

def balanced_braces(arg):
    if '{' not in arg:
        return ''
    chars = []
    n = 0
    for c in arg:
        if c == '{':
            if n > 0:
                chars.append(c)
            n += 1
        elif c == '}':
            n -= 1
            if n > 0:
                chars.append(c)
            elif n == 0:
                return ''.join(chars).lstrip().rstrip()
        elif n > 0:
            chars.append(c)
    return ''

def __deps_list_eclipse(list, project):
    prop = parse_properties(os.path.join(project, 'project.properties'))
    for i in range(1,100):
        dep = prop.get('android.library.reference.%d' % i)
        if dep:
            absdep = os.path.abspath(os.path.join(project, dep))
            __deps_list_eclipse(list, absdep)
            if not absdep in list:
                list.append(absdep)

def __deps_list_gradle(list, project):
    with open(os.path.join(project, 'build.gradle'), 'r') as f:
        str = f.read()
    # remove comments in groovy
    str = re.sub(r'''(/\*([^*]|[\r\n]|(\*+([^*/]|[\r\n])))*\*+/)|(//.*)''', '', str)
    ideps = []
    # for depends in re.findall(r'dependencies\s*\{.*?\}', str, re.DOTALL | re.MULTILINE):
    for m in re.finditer(r'dependencies\s*\{', str):
        depends = balanced_braces(str[m.start():])
        for proj in re.findall(r'''compile project\(.*['"]:(.+)['"].*\)''', depends):
            ideps.append(proj.replace(':', '/'))
    if len(ideps) == 0:
        return

    path = project
    for i in range(1, 3):
        path = os.path.abspath(os.path.join(path, os.path.pardir))
        b = True
        deps = []
        for idep in ideps:
            dep = os.path.join(path, idep)
            if not os.path.isdir(dep):
                b = False
                break
            deps.append(dep)
        if b:
            for dep in deps:
                __deps_list_gradle(list, dep)
                list.append(dep)
            break

def deps_list(dir):
    if is_gradle_project(dir):
        list = []
        __deps_list_gradle(list, dir)
        return list
    else:
        list = []
        __deps_list_eclipse(list, dir)
        return list

def package_name(dir):
    path = os.path.join(dir, 'AndroidManifest.xml')
    if os.path.isfile(path):
        with open(path, 'r') as manifestfile:
            data = manifestfile.read()
            return re.findall('package=\"([\w\d_\.]+)\"', data)[0]

def cexec(args, failOnError = True):
    p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()
    if failOnError and p.returncode != 0:
        print('Fail to exec %s'%args)
        print(output)
        print(err)
        exit(1)
    return output

def get_android_jar(path):
    if not os.path.isdir(path):
        return None
    platforms = os.path.join(path, 'platforms')
    if not os.path.isdir(platforms):
        return None
    api = 0
    result = None
    for pd in os.listdir(platforms):
        pd = os.path.join(platforms, pd)
        if os.path.isdir(pd) and os.path.isfile(os.path.join(pd, 'source.properties')) and os.path.isfile(os.path.join(pd, 'android.jar')):
            with open(os.path.join(pd, 'source.properties'), 'r') as f:
                s = f.read()
                m = re.search(r'^AndroidVersion.ApiLevel\s*[=:]\s*(.*)$', s, re.MULTILINE)
                if m:
                    a = int(m.group(1))
                    if a > api:
                        api = a
                        result = os.path.join(pd, 'android.jar')
    return result

def find_android_jar(dir):
    if os.path.isfile(os.path.join(dir, 'local.properties')):
        with open(os.path.join(dir, 'local.properties'), 'r') as f:
            s = f.read()
            m = re.search(r'^sdk.dir\s*[=:]\s*(.*)$', s, re.MULTILINE)
            if m:
                r = get_android_jar(m.group(1))
                if r:
                    return r

    if os.getenv('ANDROID_HOME'):
        r = get_android_jar(os.getenv('ANDROID_HOME'))
        if r:
            return r

    if os.getenv('ANDROID_SDK'):
        r = get_android_jar(os.getenv('ANDROID_SDK'))
        if r:
            return r

    r = get_android_jar(os.path.expanduser('~/Library/Android/sdk'))
    if r:
        return r

    r = get_android_jar('/Applications/android-sdk-mac_86')
    if r:
        return r

    r = get_android_jar('/android-sdk-mac_86')
    if r:
        return r

if __name__ == "__main__":

    dir = '.'
    if len(sys.argv) > 1:
        dir = sys.argv[1]

    pn = package_name(dir)

    android_jar = find_android_jar(dir)
    if not android_jar:
        print('android.jar not found !!!\nUse local.properties or set ANDROID_HOME env')

    if is_gradle_project(dir):
        print('cast project as gradle project')
    else:
        print('cast project as eclipse project')

    for i in range(0, 32):
        cexec(['adb', 'forward', 'tcp:41128', 'tcp:%d'%(41128+i)])
        output = cexec(['curl', 'http://127.0.0.1:41128/packagename'], failOnError = False).strip()
        if output == pn:
            print('found package '+pn+' at port %d'%(41128+i))
            break
        if i == 31:
            cexec(['adb', 'forward', '--remove', 'tcp:41128'], failOnError = False)
            print('package ' + pn + ' not found')
            exit(1)

    if not os.path.exists('bin/lcast/values'):
        os.makedirs('bin/lcast/values')

    cexec(['curl', '--silent', '--output', 'bin/lcast/values/ids.xml', 'http://127.0.0.1:41128/ids.xml'])
    cexec(['curl', '--silent', '--output', 'bin/lcast/values/public.xml', 'http://127.0.0.1:41128/public.xml'])

    aaptargs = ['aapt', 'package', '-f', '--auto-add-overlay', '-F', 'bin/res.zip']
    for dep in deps_list(dir):
        aaptargs.append('-S')
        aaptargs.append(os.path.join(dep, 'res'))
    aaptargs.append('-S')
    aaptargs.append('res')
    aaptargs.append('-S')
    aaptargs.append('bin/lcast')
    aaptargs.append('-M')
    aaptargs.append('AndroidManifest.xml')
    aaptargs.append('-I')
    aaptargs.append(android_jar)
    cexec(aaptargs)

    print('upload and cast..')
    cexec(['curl', '--silent', '-T', 'bin/res.zip', 'http://127.0.0.1:41128/pushres'])
    cexec(['curl', '--silent', 'http://127.0.0.1:41128/lcast'])
