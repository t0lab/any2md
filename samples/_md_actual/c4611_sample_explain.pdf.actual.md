# Pdf Bookmark Sample

| Sample Date: | May 2001 |
| Prepared by: | Accelio Present Applied Technology |
| Created and Tested Using: | • Accelio Present Central 5.4<br>• Accelio Present Output Designer 5.4 |
| Features Demonstrated: | • Primary bookmarks in a PDF file.<br>• Secondary bookmarks in a PDF file. |

## Overview

This sample consists of a simple form containing four distinct fields. The data file contains eight separate records.

By default, the data file will produce a PDF file containing eight separate pages. The selective use of the bookmark file will produce the same PDF with a separate pane containing bookmarks. This screenshot of the sample output shows a PDF file with bookmarks.

**[Image - pdf_page #1]**
Screenshot of "Acrobat Reader - [ap_bookmark.pdf]".
Menu bar: File Edit Document View Window Help
Left pane (Bookmarks/Thumbnails tab):
- Invoices by Date
  - 2000-01-1
  - 2000-01-2
  - 2000-01-3
  - 2000-01-4
  - 2000-01-5
  - 2000-01-6
  - 2000-01-7
  - 2000-01-8
Right pane (Document view):
Date 2000-01-1
Description Description for item # 1
Type TYPE1
Amount 11.00

The left pane displays the available bookmarks for this PDF. You may need to enable the display of bookmarks in Adobe® Acrobat® Reader by clicking Window > Show Bookmarks. Selecting a date from the left pane displays the corresponding page within the document.

Note that the index has been sorted according to the specification in the bookmark file, and that pages within the file are created according to the original order in the data file.

## Sample Data File

```
^reformat trunc
^symbolset WINLATIN1
^field trans_date
2000-01-1
^field description
Description for item #1
^field trans_type
TYPE1
^field trans_amount
11.00
^page 1
^field trans_date
2000-01-2
^field description
Description for item #2
^field trans_type
TYPE2
^field trans_amount
11.00
^page 1
^field trans_date
2000-01-3
^field description
Description for item #3
^field trans_type
TYPE3
```

## Sample Bookmark File

```
[invoices]
Invoices by Date=0
trans_date=1,A
[type]
Invoices by Item Type=0
trans_type=1,A
[amount]
Invoices by Transaction Amount=0
trans_amount=1,D
```

The example bookmark file includes three distinct sections:

- Invoices sorted, ascending, by date.
- Invoices sorted, ascending, by item type.
- Invoices sorted, descending, by transaction amount.

## Sample Files

This sample package contains:

| Filename | Description |
|---|---|
| ap_bookmark.IFD | The template design. |
| ap_bookmark.mdf | The template targeted for PDF output. |
| ap_bookmark.dat | A sample data file in DAT format. |
| ap_bookmark.bmk | A sample bookmark file. |
| ap_bookmark.pdf | Sample PDF output. |
| ap_bookmark_doc.pdf | A document describing the sample. |

## Deploying the Sample

To deploy this sample in your environment:

1. Open the template design ap_bookmark.IFD in Output Designer and recompile the template for the appropriate presentment target.
2. Modify the -z option in the ^job command in the data file ap_bookmark.dat to:
   - Identify the target output device.
   - Identify the bookmark file using the -abmk command.
   - Identify the section for which to generate bookmarks, if desired, using the -abms command.

For example,

| To bookmark by … | Use the command line parameter … |
|---|---|
| Invoices | -abmkap_bookmark.bmk -abmsinvoices |
| Type | -abmkap_bookmark.bmk -abmstype |
| Amount | -abmkap_bookmark.bmk -abmsamount |

3. Place the accompanying files in directories consistent with your implementation:
   - Place ap_bookmark.IFD in the Designs subdirectory for Output Designer.
   - Place ap_bookmark.mdf in the forms subdirectory accessible to Central.
   - Place ap_bookmark.bmk in an addressable directory.

## Running the Sample

- To run this sample, place ap_bookmark.dat in the collector directory scanned by Central.