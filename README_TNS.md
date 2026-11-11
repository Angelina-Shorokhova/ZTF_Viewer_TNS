# TNS Submission Module for SNAD ZTF Viewer

This module adds a page to the SNAD ZTF Viewer for automated report submission to the Transient Name Server (TNS).

## File Structure

The module consists of three main files:

### 1. `ztf_viewer/pages/submit_tns.py` (UI and Page Logic)
Handles the page display and user interaction.
*   `get_layout()`: Builds the HTML page. Checks authorization (`akb_token` cookie) and loads the username.
*   `update_plot()`: Callback to rebuild the plot when `Refmag` or `MJD start` changes.
*   `update_generated_text()`: Callback to generate the "Report Review" table and hidden JSON preview.
*   `handle_submit()`: Main submission callback. Checks for duplicates, uploads the plot image, builds the payload, submits to TNS, and updates the catalog.

### 2. `ztf_viewer/tns/helpers.py` (Backend and API)
Contains data processing and external API requests.
*   `load_snad_data()`: Downloads the light curve CSV from SNAD.
*   `get_meta()`: Gets coordinates and searches for the `ZTF Alert ID` in ALeRCE and Fink.
*   `get_snad_name_from_catalog()`: Searches for the object's name in the `SNAD_catalog_master` Google Sheet (or generates a new name).
*   `enrich_data()` / `find_first_detection()`: Recalculates fluxes/errors and finds the first detection point on the curve.
*   `validate_internal_name()`: Checks if the year in the `ZTF Alert ID` matches the discovery year. If not, replaces it with the SNAD name.
*   `is_already_submitted()`: Checks TNS for existing submissions (blocks if the date difference is less than 30 days).
*   `upload_file_to_tns()`: Downloads the PNG plot from SNAD and uploads it to TNS.
*   `submit_report()`: Sends the final JSON to the TNS API and retrieves the assigned name.
*   `update_snad_catalog()`: Sends successful report data to Google Apps Script (which writes it to the online sheet).

### 3. `ztf_viewer/tns/plot.py` (Visualization)
*   `build_lightcurve_figure()`: Builds the interactive light curve plot. Shows a readable date on hover.

## Environment Variables (`secret.env`)
Required keys for the module:
*   `TNS_API_KEY`: TNS API key (Sandbox or Production).
*   `GOOGLE_SCRIPT_URL`: Google Apps Script web app URL.
*   `GOOGLE_SHEET_TOKEN`: Secret token for Google Sheet authentication.

## Workflow
1. User opens `/submit-tns?oid=...`.
2. Code loads the light curve and metadata (ALeRCE/Fink/Google).
3. User adjusts `MJD start` and `Refmag` to highlight the flare on the plot.
4. A report summary is generated; user reviews the data (RA/DEC, date, type).
5. On "Submit", the code:
   - Checks for duplicates in TNS.
   - Uploads the plot image to TNS.
   - Submits the AT report.
   - Appends the record to the SNAD Catalog Master.
