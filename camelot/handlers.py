# -*- coding: utf-8 -*-

import os
import sys

#from PyPDF2 import PdfFileReader, PdfFileWriter
import fitz

from .core import TableList
from .parsers import Stream, Lattice
from .utils import (
    TemporaryDirectory,
    get_page_layout,
    get_text_objects,
    get_rotation,
    is_url,
    download_url,
)


class PDFHandler(object):
    """Handles all operations like temp directory creation, splitting
    file into single page PDFs, parsing each PDF and then removing the
    temp directory.

    Parameters
    ----------
    filepath : str
        Filepath or URL of the PDF file.
    pages : str, optional (default: '1')
        Comma-separated page numbers.
        Example: '1,3,4' or '1,4-end' or 'all'.
    password : str, optional (default: None)
        Password for decryption.

    """

    def __init__(self, filepath, pages="1", password=None):
        if is_url(filepath):
            filepath = download_url(filepath)
        self.filepath = filepath
        if not filepath.lower().endswith(".pdf"):
            raise NotImplementedError("File format not supported")

        if password is None:
            self.password = ""
        else:
            self.password = password
            if sys.version_info[0] < 3:
                self.password = self.password.encode("ascii")
        self.pages = self._get_pages(self.filepath, pages)

    def _get_pages(self, filepath, pages):
        """Converts pages string to list of ints.

        Parameters
        ----------
        filepath : str
            Filepath or URL of the PDF file.
        pages : str, optional (default: '1')
            Comma-separated page numbers.
            Example: '1,3,4' or '1,4-end' or 'all'.

        Returns
        -------
        P : list
            List of int page numbers.

        """
        page_numbers = []
        if pages == "1":
            page_numbers.append({"start": 1, "end": 1})
        else:
            instream = open(filepath, "rb")
            infile = fitz.open(instream)
            if infile.isEncrypted:
                infile.decrypt(self.password)
            if pages == "all":
                page_numbers.append({"start": 1, "end": infile.getNumPages()})
            else:
                for r in pages.split(","):
                    if "-" in r:
                        a, b = r.split("-")
                        if b == "end":
                            b = infile.getNumPages()
                        page_numbers.append({"start": int(a), "end": int(b)})
                    else:
                        page_numbers.append({"start": int(r), "end": int(r)})
            instream.close()
        P = []
        for p in page_numbers:
            P.extend(range(p["start"], p["end"] + 1))
        return sorted(set(P))

    def _save_page(self, filepath, page, temp):
        """Saves specified page from PDF into a temporary directory.

        Parameters
        ----------
        filepath : str
            Filepath or URL of the PDF file.
        page : int
            Page number.
        temp : str
            Tmp directory.

        """
        with open(filepath, "rb") as fileobj:
            infile = fitz.open(fileobj)
            if infile.isEncrypted:
                infile.decrypt(self.password)
            fpath = os.path.join(temp, f"page-{page}.pdf")
            froot, fext = os.path.splitext(fpath)
            #p = infile.loadPage(page - 1)
            outfile = fitz.open()
            outfile.insert_pdf(infile, to_page=page-1, from_page=page-1)
            """
            with open(fpath, "wb") as f:
                outfile.write(f)
            """
            outfile.save(fpath)
            layout, dim = get_page_layout(fpath)
            # fix rotated PDF
            chars = get_text_objects(layout, ltype="char")
            horizontal_text = get_text_objects(layout, ltype="horizontal_text")
            vertical_text = get_text_objects(layout, ltype="vertical_text")
            rotation = get_rotation(chars, horizontal_text, vertical_text)
            if rotation != "":
                fpath_new = "".join([froot.replace("page", "p"), "_rotated", fext])
                os.rename(fpath, fpath_new)
                instream = open(fpath_new, "rb")
                infile = fitz.open(instream)
                if infile.isEncrypted:
                    infile.decrypt(self.password)
                outfile = fitz.open()
                p = infile.loadPage(0)
                if rotation == "anticlockwise":
                    p.rotate(90)
                elif rotation == "clockwise":
                    p.rotate(270)
                outfile.insert_pdf(p)
                """
                with open(fpath, "wb") as f:
                    outfile.write(f)
                """
                outfile.save(fpath)
                instream.close()

    def parse(
        self, flavor="lattice", suppress_stdout=False, layout_kwargs={}, **kwargs
    ):
        """Extracts tables by calling parser.get_tables on all single
        page PDFs.

        Parameters
        ----------
        flavor : str (default: 'lattice')
            The parsing method to use ('lattice' or 'stream').
            Lattice is used by default.
        suppress_stdout : str (default: False)
            Suppress logs and warnings.
        layout_kwargs : dict, optional (default: {})
            A dict of `pdfminer.layout.LAParams <https://github.com/euske/pdfminer/blob/master/pdfminer/layout.py#L33>`_ kwargs.
        kwargs : dict
            See camelot.read_pdf kwargs.

        Returns
        -------
        tables : camelot.core.TableList
            List of tables found in PDF.

        """
        tables = []
        with TemporaryDirectory() as tempdir:
            for p in self.pages:
                self._save_page(self.filepath, p, tempdir)
            pages = [os.path.join(tempdir, f"page-{p}.pdf") for p in self.pages]
            parser = Lattice(**kwargs) if flavor == "lattice" else Stream(**kwargs)
            for p in pages:
                t = parser.extract_tables(
                    p, suppress_stdout=suppress_stdout, layout_kwargs=layout_kwargs
                )
                tables.extend(t)
        return TableList(sorted(tables))
