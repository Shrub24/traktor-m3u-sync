# Engine → Pioneer USB spike

Test whether rbxport can build a playable USB tree using Engine's existing timing and key, without routing through XML or running another beat/key detector. Keep the proof standalone: read a copied Engine 5 database, translate selected tracks into an export job, and render to a new directory. No writes to Engine, no USB importer, and no changes to the CLI, store or NixOS jobs.
