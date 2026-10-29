cd chemin\vers\le\dossier
del carcassonne_model.pt
python neural_evaluator.py train D:\chemin\vers\mes_parties 200

Et dans firefox 

about:debugging, 
pointez le manifest.json vers ce nouveau dossier. 
cd ..
python replay_bga.py parties