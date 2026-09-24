# Paper processing assets

`icons/` contains 48 image templates for the literature retrieval workflow.
The image bytes are unchanged; filenames use neutral publisher identifiers.
Checksums and workflow references are recorded in `manifest.json`.

| Filename pattern | Use |
| --- | --- |
| `publisher_A_*.png` | Publisher A actions |
| `publisher_E_*.png` | Publisher E actions |
| `publisher_R_*.png` | Publisher R actions |
| `publisher_S_*.png` | Publisher S actions |
| `publisher_W_*.png` | Publisher W actions |
| `publisher_*_SI_*.png` | Supporting-information actions |

The paper downloader selects numbered templates such as `publisher_A_1.png`
and `publisher_A_2.png`. The SI downloader selects the template names explicitly
referenced by each publisher flow. Nine templates are used by the paper flows and 33 by the SI flows.

## SI entry templates

`publisher_W_SI_1.png` provides the required Publisher W entry template.

The optional `publisher_S_SI_Accept2.png` cookie-button alternative remains absent.

Capture missing or outdated templates from the browser configuration used for
literature retrieval. Screen resolution, display
scaling, and browser zoom affect image matching.

## Additional archived images

The following images are retained but are not referenced by the download flows:

- `publisher_R_SI_1_alt.png`
- `publisher_W_1_copy.png`
- `publisher_W_SI_3bbb.png`
- `publisher_W_download.png`
- `print.png`
- `verification_challenge.png`

The alternate SI image and copied paper image have distinct filenames so they
cannot replace the active templates accidentally. The verification image is
retained as an unused asset; the downloader does not solve verification challenges.

Neutral filenames do not alter the contents of the image templates.
