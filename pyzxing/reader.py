import ast
import glob
import os.path as osp
import re

import subprocess

from pathlib import Path
import tempfile
from joblib import Parallel, delayed

LIB_PATH = Path(__file__).absolute().parent / 'jar' / 'javase-3.4.2-SNAPSHOT-jar-with-dependencies.jar'


class BarCodeReader:
    lib_path = ""

    def __init__(self, lib_path=LIB_PATH):
        self.lib_path = str(lib_path)

    def decode(self, filename_pattern):
        filenames = glob.glob(osp.abspath(filename_pattern))
        if not len(filenames):
            raise FileNotFoundError

        elif len(filenames) == 1:
            results = self._decode(filenames[0].replace('\\', '/'))

        else:
            results = Parallel(n_jobs=-1)(
                delayed(self._decode)(filename.replace('\\', '/'))
                for filename in filenames)

        return results

    def decode_array(self, array):
        from PIL import Image
        with tempfile.NamedTemporaryFile(suffix=".png") as fp:
            Image.fromarray(array).save(fp)
            result = self.decode(fp.name)

        return result

    def _decode(self, filename):
        cmd = ' '.join(
            ['java -jar', self.lib_path, 'file:///' + filename, '--multi', '--try_harder'])
        (stdout, _) = subprocess.Popen(cmd,
                                       stdout=subprocess.PIPE,
                                       # universal_newlines=True,
                                       shell=True).communicate()
        lines = stdout.splitlines()
        separator_idx = [
                            i for i in range(len(lines)) if lines[i].startswith(b'file')
                        ] + [len(lines)]

        result = [
            self._parse_single(lines[separator_idx[i]:separator_idx[i + 1]])
            for i in range(len(separator_idx) - 1)
        ]
        return result

    @staticmethod
    def _parse_single(lines):
        """parse stdout and return structured result

            raw stdout looks like this:
            file://02.png (format: CODABAR, type: TEXT):
            Raw result:
            0000
            Parsed result:
            0000
            Found 2 result points.
            Point 0: (50.0,202.0)
            Point 1: (655.0,202.0)
        """
        result = dict()
        result['filename'] = lines[0].split(b' ', 1)[0]

        if len(lines) > 1:
            lines[0] = lines[0].split(b' ', 1)[1]
            for ch in [b'(', b')', b':', b',']:
                lines[0] = lines[0].replace(ch, b'')
            _, result['format'], _, result['type'] = lines[0].split(b' ')

            raw_index = find_line_index(lines, b"Raw result:", 1)
            parsed_index = find_line_index(lines, b"Parsed result:", raw_index)
            points_index = find_line_index(lines, b"Found", parsed_index)

            if not raw_index or not parsed_index or not points_index:
                raise Exception("Parse Error")

            result['raw'] = b'\n'.join(lines[raw_index + 1:parsed_index])
            result['parsed'] = b'\n'.join(lines[parsed_index + 1:points_index]).replace(b"{FNC1}", b'\x1d')

            points_num = int(re.search(r"(?<=Found )\d?", lines[points_index].decode()).group())
            result['points'] = [
                ast.literal_eval(line.split(b": ")[1].decode())
                for line in lines[points_index + 1:points_index + 1 + points_num]
            ]

        return result


def find_line_index(lines, content, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(content):
            return i

    return None
