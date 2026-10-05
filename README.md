![Version](https://img.shields.io/github/v/release/MarkGotham/species?display_name=tag)
[![DOI](https://zenodo.org/badge/747293703.svg)](https://doi.org/10.5281/zenodo.18442041)
![GitHub repo size](https://img.shields.io/github/repo-size/MarkGotham/species)
![License](https://img.shields.io/badge/License-MIT-blue.svg)


# Species Counterpoint

Johann Joseph Fux's iconic pedagogical treatise,
'Gradus ad Parnassum' teaches counterpoint in a
series of examples centered on 123 exercises in three parts:
1. Part I: exercises in 2 voices (46 exercises)
2. Part II: exercises in 3 voices (45 exercises)
3. Part III: exercises in 4 voices (32 exercises)

For each of these sections, we provide four files:

1. Exercises: all of the cantus firmus exercises with only the cantus firmus present.
2. Solutions: all of Fux’s solutions to those exercises – i.e. both the cantus firmus and the additional part(s).
3. Annotations:
Those solutions annotated with every interval
formed between each additional part and the cantus firmus.
Compound intervals are included (`P5` vs `P12`) and include quality (`m3` vs `M3`).
This includes cases (e.g., species 4) where the cantus firmus moves against a tied note in the additional parts.
4. Distinct:
One for ech combination of cantus firmus (x6: d, e, f, g, a, c) and voice
(1,2 in 2 voices; 1,2,3 in 3; 1,2,3,4 in 4).
This amounts to 12 (6x2) distinct 2-voice exercises, 18 for 3 voices, and 24 in 4 voices. 
All Fux's exercises are based on this format, so these simple files distill all possibilities:
you can use this file to do any species exercise, on any cantus firmus, in any part arrangement.

Everything is provided in an editable format for teachers to adjust freely for their own class’ needs
and released under a correspondingly open licence.

Each exercise includes the following information:
- Figure number.
This is the only element based on the modern Norton/Mann edition, 1965.
This edition numbers all full exercises and associated examples,
hence the gaps in our numbering, e.g., starting here at no.5.  
- Species type (1–5),
- Modal final (d, e, f, g, a, c),
- Which of the parts has the cantus firmus

## Directory structure

Fux's three parts (called 'EXERCITII' in the original)
are each split into 5 species
(e.g., called 'De quinta Specie Contrapundi' for 5th species).
This repository is organised likewise.
The paired krn and json files for individual examples are always at the deepest level
and stand as the canonical versions of record (VoR);
all other files are derived from them.

The only exceptions are:
- source PDFs directly from the
[1725 edition (click here for the IMSLP page)](https://imslp.org/wiki/Gradus_ad_Parnassum_(Fux,_Johann_Joseph))
which do not divide evenly by exercise and therefore
have [their own top-level directory and one file per page](./source_pdf);
- various [scripts for processing this data](./scripts),
including the derived files as discussed here.

Derived files include the mxl conversions for each exercise,
and combined files each structural level
(for each part and species).
There is a grouping for
`./I/sp1/ex1sp1.mxl`
and
`./I/ex1.mxl`
each containing all files at that level or deeper.

All together then the structure is as follows:

```
./

├── I/                      # Part I or 'EXERCITII I' in Fux's original
│   ├── ex1_exercise.mxl    # derived file (do not edit), all exercises (no solutions) in the current part.
│   ├── ex1.mxl             # derived file, all exercises, with solutions.
│   ├── I-Annotations.mscz  # Public-facing, manually edited from the derived files (as discussed below)
│   ├── ...                 # further public-facing, manually edited file (as discussed below)
│   ├── sp1/                # Part I, Species 1 (Fux calls these 'Lectio'; we avoid that term here)
│   │   ├── ex1sp1.mxl      # derived file group all exercises in Part I, Species 1
│   │   ├── gap_005.krn     # canonical, VoR score file for exercise (figure) 5
│   │   ├── gap_005.json    # complementary canonical VoR metadata file for exercise (figure) 5
│   │   ├── gap_005.mxl     # derived file converted from the krn (do not edit)
│   │   ├── gap_006.krn     # next score file, same pattern
│   │   ├── ...
│   │   └── gap_023.mxl     # last file for this Part and Species.
│   ├── sp2/
│   ├── ...
│   └── sp5/
├── II/
├── III/
├── scripts/                # All code for generating derived files, and for various checks.
└── source_pdf/             # One PDF file per _page_, hence not mixing with the above
```


## Downloads

### Whole Part Downloads (Part I, II, III)

You can download a whole part at once directly
and in your choice of format: .pdf, .mscz, or .mxl.
PDFs are known to most and not the main use case here.
The .mscz format is for the MuseScore Studio app specifically;
you can open the .mxl files in almost any music notation software (MuseScore, Sibelius, Dorico, ...).

| Part | Exercises                                                                                         | Solutions                                                                                         | Annotations                                                                                             | Distinct                                                                                       |
|------|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| I    | [.mxl](./I/I-Exercises.mxl),[.mscz](./I/I-Exercises.mscz),[.pdf](./I/I-Exercises.pdf)             | [.mxl](./I/I-Solutions.mxl),[.mscz](./I/I-Solutions.mscz),[.pdf](./I/I-Solutions.pdf)             | [.mxl](./I/I-Annotations.mxl),[.mscz](./I/I-Annotations.mscz),[.pdf](./I/I-Annotations.pdf)             | [.mxl](./I/I-Distinct.mxl),[.mscz](./I/I-Distinct.mscz),[.pdf](./I/I-Distinct.pdf)             |
| II   | [.mxl](./II/II-Exercises.mxl),[.mscz](./II/II-Exercises.mscz),[.pdf](./II/II-Exercises.pdf)       | [.mxl](./II/II-Solutions.mxl),[.mscz](./II/II-Solutions.mscz),[.pdf](./II/II-Solutions.pdf)       | [.mxl](./II/II-Annotations.mxl),[.mscz](./II/II-Annotations.mscz),[.pdf](./II/II-Annotations.pdf)       | [.mxl](./II/II-Distinct.mxl),[.mscz](./II/II-Distinct.mscz),[.pdf](./II/II-Distinct.pdf)       |
| III  | [.mxl](./III/III-Exercises.mxl),[.mscz](./III/III-Exercises.mscz),[.pdf](./III/III-Exercises.pdf) | [.mxl](./III/III-Solutions.mxl),[.mscz](./III/III-Solutions.mscz),[.pdf](./III/III-Solutions.pdf) | [.mxl](./III/III-Annotations.mxl),[.mscz](./III/III-Annotations.mscz),[.pdf](./III/III-Annotations.pdf) | [.mxl](./III/III-Distinct.mxl),[.mscz](./III/III-Distinct.mscz),[.pdf](./III/III-Distinct.pdf) |

### Individual figures (5, 6, 11, ..., 204)

We also provide each figure in a separate file.
These can be downloaded or viewed and engaged with directly online.
The best way to explore this collection is via
[the searchable and sortable html summary](./species_contents.html).

This html can be opened in any web browser and used
to search the collection by any of the criteria above (e.g., species type). 


## Cantus firmus

Fux's use of cantus firmus broadly centres on
one cantus firmus for each modal final that stays broadly constant
throughout all exercises and parts.

Some variants are noted immediately below,
followed by the usage counts over all (by species and by modal final)

| Modal final | Typical Pitches                                        | Variants                                                                                    |
|-------------|--------------------------------------------------------|---------------------------------------------------------------------------------------------|
| D           | D4, F4, E4, D4, G4, F4, A4, G4, F4, E4, D4             | Two octaves: D3 and D4                                                                      |
| E           | E4, C4, D4, C4, A3, A4, G4, E4, F4, E4                 | Three octaves: E3, E4 and E5 (fig.184)                                                      |
| F           | F3, G3, A3, F3, D3, E3, F3, C4, A3, F3, G3, F3         | Two octaves: F3 and F4                                                                      |
| G           | G3, C4, B3, G3, C4, E4, D4, G4, E4, C4, D4, B3, A3, G3 | None                                                                                        |
| A           | A3, C4, B3, D4, C4, E4, F4, E4, D4, C4, B3, A3         | Three octaves (A2, A3 and A4); some lack the first D (e.g., fig.42: A3, C4, B3, C4, E4 ...) |
| C           | C4, E4, F4, G4, E4, A4, G4, E4, F4, E4, D4, C4         | One related, but more substantially different form: C4, D4, F4, E4, G4, E4, F4, E4, D4, C4  |

### Counts by species

| Part  | Species 1 | Species 2 | Species 3 | Species 4 | Species 5 | Total exercises |
|-------|-----------|-----------|-----------|-----------|-----------|-----------------|
| I     | 10        | 12        | 6         | 6         | 12        | 46              |
| II    | 16        | 9         | 5         | 9         | 6         | 45              |
| III   | 11        | 4         | 8         | 4         | 5         | 32              |
| Total | 37        | 25        | 19        | 19        | 23        | 123             |

### Counts by modal final

| Modal final | Part I (46) | Part II (45) | Part III (32) | Total |
|-------------|-------------|--------------|---------------|-------|
| D           | 10          | 17           | 21            | 48    |
| E           | 10          | 12           | 7             | 29    |
| F           | 10          | 9            | 4             | 23    |
| G           | 6           | 2            | 0             | 8     |
| A           | 6           | 3            | 0             | 9     |
| C           | 4           | 2            | 0             | 6     |
| Total       | 46          | 45           | 32            | 123   |

## Review

Over the course of processing,
we round trip check at least once, most formally with `match_check`.

E.g.:
- Checking conversions with:
`../I/sp1/gap_005.krn ../I/sp1/gap_005.mxl`
- Check manually formatted files have not inadvertently changed any notes:
`../I/I-Solutions.mxl ../I/ex1.mxl`


## Layout

For both consistency, and labour-saving, this version adds programmatic handling of:
- System breaks: setting them in relation to note density (lowest in species 1, high in 3 and 5)
- Modern clef choice: selecting the "best" from among the three modern standards:
treble, treble8, and bass.

Manual layout work is now limited to two elements:
First is the hiding of courtesy clefs.
This cannot currently be passed (reliably) through the requisite formats and code libraries.
It can be handled with a MuseScore style file, but that is not obviously less work than doing it manually.

Second, the flagship 12 public-facing files
(4 for each of the three parts)
are checked for layout,
with manual edits including a preference for setting
page breaks such that they
do fall between each species, do not come mid-exercise,
and generally balance the number of systems per page.
Some, perhaps most of this could be automated, and may yet be,
but there's a point at which you might want to do a manual final check of scores,
and doing this as part of that, is not labour-intensive.

The layout is set for MuseScore 4.7.X.
Layout should be relatively flexible and maintainable between formats and versions,
though layout remains one of the most common forms of breaking changes between MuseScore versions, and in general.
The default page size and orientation is A4 portrait,
But of course, the main point of having editable files is that users can choose their own preferences.
Alternative "US-Letter" page size is provided for the final PDFs,
in light of the non-computational musician and pedagogue users.  


## Acknowledgements, Contribution, and Licence

Thanks to Jay Wilson for the initial transcriptions and permission to use them for this expanded initiative.
All subsequent annotation, analysis, code etc. by me (Mark Gotham).
Thanks to my Open Music Theory (OMT) colleagues for allowing me to present this material there
and to the many OMT users who have been in touch with corrections (3 to date) and nice comments.

Contributions are welcome.
Please submit a PR (e.g., an edit to the krn or json VoR files),
or raise an issue,
or simply [get in touch](https://markgotham.github.io/) 
and I'll get on it.

Licence:
- Mark Gotham
- Code = MIT licence, 2026
- Rendered scores = CC0 (Public Domain). Mark Gotham and FourScoreAndMore.org waive all rights to those documents.
