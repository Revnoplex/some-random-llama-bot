# DOCUMENTATION FOR MERGING A PATCH RELEASE BRANCH WITHOUHT INFECTING IT WITH CHANGES FROM MAIN:
1. Make sure you are on main:
    ```bash
    git checkout main
    ```
    Also make sure everything is up-to-date (optional):
    ```bash
    git pull
    ```
2. Merge your patch branch into main:
    ```bash
    git merge patch-branch-name
    ``` 
3. Make sure it is tracking properly (not 100% sure if this is needed):
    ```bash
    git push -u origin main
    ```
4. Resolve any conflicts if any appeared after running the command in step 2, then add the file:
    ```bash
    git add path/to/resolved-conflict-file
    ```
5. Then run git commit (not sure if this is needed if there was no conflict):
    ```bash
    git commit
    ```
6. Push to GitHub, hopefully it accepts it:
    ```bash
    git push
    ```