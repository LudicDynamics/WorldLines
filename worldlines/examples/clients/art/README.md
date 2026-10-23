# Art packs for the client examples

One folder per world: `<world>/art.json` says which picture goes with which place, person, ending and clue, where the
rooms sit on the map, and which variables are shown as meters. Both examples (`../ts`, `../godot`) read the same pack.

`bash pull.sh [world]` copies the pictures from the asset workshop (`$WORLDLINES_ASSETS_DIR/worlds/<world>/`) and the
template, resized for the web; anything not drawn yet is reported and the games draw a placeholder.
