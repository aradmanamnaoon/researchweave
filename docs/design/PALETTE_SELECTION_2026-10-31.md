# ResearchWeave palette selection: Meridian

Source: Rust/Slint desktop `Theme` and `display_contrast.rs`, isolated mission branch based on `976656d`. Candidate directions were considered for multi-hour scientific reading, tables and manuscript work. This is a code-level design decision; testing with representative real users and new GUI screenshots remains open.

| Candidate | Identity | Contrast and design rationale | Outcome |
| --- | --- | --- | --- |
| Existing Deep Ink / Teal | Deep navy, green-teal, violet and copper | Familiar institutional-scientific feel, but already seen throughout existing UI, not a new identity | Replaced |
| **Meridian** | Mineral Blue `#3B5B88`, Ink `#202B37`, Amethyst `#6957A6`, Clay `#9B6042`, Warm Paper `#F5F4EF` | Calm blue central emphasis, neutral reading surfaces, accessible foreground/background pairs and distinct evidence/data roles | **Selected and implemented in central theme** |
| Botanical Sage / Umber | Dark green, tan and umber | Softer editorial feel but less separation between statuses and scientific chart series without more treatments | Deferred |

## Selected semantic roles

| Role | Light | Dark |
| --- | --- | --- |
| Application canvas | `#F5F4EF` | `#111B26` |
| Raised surface | `#EAEFF2` | `#243544` |
| Body foreground | `#202B37` | `#F5F7FA` |
| Muted foreground | `#566574` | `#C2CFDC` |
| Primary accent | `#3B5B88` | `#98BCD5` |
| Focus/evidence | `#6957A6` | `#B4A0E4` |
| Discovery | `#9B6042` | `#E4A880` |
| Navigation surface | `#263245` | `#172638` |
| Navigation text | `#C7D6E1` | `#C7D6E1` |

## Verification

WCAG 2.x relative-luminance calculations for the code-defined text/surface pairs: light primary action on white **6.91:1**; dark primary on dark surface **7.32:1**; light muted body on canvas **5.43:1**; light evidence on white **5.98:1**; light clay on paper **4.60:1**. The Rust test checks at least 4.5:1 for these semantic roles, and an additional test ties sampled role values to their Slint declarations to detect drift.

The activity rail now has a dedicated hover token, and status text uses a foreground with readable navigation contrast. The manuscript body has a taller neutral reading canvas with an inset margin, and the notebook entry area has more usable height. These are interface improvements, **not** Word-format parity, Google Keep cards, or proof of GUI accessibility at multiple scales. Host-native control tint, old screenshots/branding, screen-reader/IME and cross-platform rendered comparison remain open.
