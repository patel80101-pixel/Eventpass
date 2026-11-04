# EventPass — End-to-End Cloud-Native Deployment on Amazon EKS

**Cloud Native Orchestration (CSA3004) project**
**Student:** Pooja Patel · **PRN:** 20240801035

EventPass is a college event registration and ticketing system built with Flask. It is containerised with Docker, stored in Amazon ECR, deployed on Amazon EKS (Kubernetes), built automatically by GitHub Actions, and kept in sync with Git by Argo CD (GitOps).

```
 You push code ──► GitHub ──► GitHub Actions ──► test ──► docker build ──► push to Amazon ECR
                                     │
                                     └──► updates image tag in k8s/deployment.yaml (commit)
                                                         │
                     Argo CD (inside EKS) watches Git ◄──┘
                                     │
                                     └──► rolls out the new version on EKS ──► AWS Load Balancer ──► Browser
```

---

## What's in this folder

| Path | What it is |
|---|---|
| `app.py`, `templates/`, `static/` | The Flask web app |
| `tests/test_app.py` | Unit tests (run automatically in the pipeline) |
| `Dockerfile` | Builds the container image (Python 3.12, gunicorn, non-root user) |
| `k8s/` | Kubernetes manifests: Namespace, Deployment (probes + resource limits), LoadBalancer Service |
| `cluster/cluster.yaml` | eksctl config: EKS cluster with 2 × t3.medium worker nodes |
| `.github/workflows/ci-cd.yaml` | CI/CD pipeline: test → build → push to ECR → update manifest |
| `argocd/application.yaml` | Argo CD application (auto-sync, self-heal, prune) |
| `iam/github-trust-policy.json` | Lets only *your* GitHub repo log in to AWS (OIDC, no keys stored) |
| `scripts/` | Helper scripts that do the long commands for you |

### App features
- **Events:** create, edit and delete events (category, venue, date, time, capacity, ticket price), plus search and category filter
- **Registration:** book 1–5 tickets per person. Seat capacity is enforced, so overbooking is impossible, and one booking per email per event
- **Digital tickets:** each booking gets a unique code like `EP-7K2M9Q` with a printable ticket page
- **Check-in desk:** staff type the ticket code at the venue. Cancelled or already-used tickets are rejected
- **Cancellation:** cancelling a booking releases the seats for others
- **Dashboard:** events, bookings, tickets sold, revenue, check-in rate, sold-out count
- **API:** `/api/events`, `/api/stats`, and `/health` (used by the Kubernetes probes)

---

## ⏱ Time and 💰 cost

- **Total time:** about 2–2.5 hours. Creating the EKS cluster alone takes ~20 minutes of waiting.
- **Cost:** about **₹30 per hour** while the cluster is running (EKS + 2 worker nodes + load balancers + NAT gateway). New AWS accounts get sign-up credits that cover this **if you finish and clean up the same day**.
- **⚠️ Do Part 12 (Cleanup) right after your demo/viva.** A forgotten cluster costs ~₹700 a day.

---

## Part 1 — Create your GitHub account (10 min)

1. Go to **https://github.com/signup** and sign up with your email. Verify the email.
2. Create the repository:
   - Click **+** (top right) → **New repository**
   - Repository name: **`eventpass`**
   - Visibility: **Public** (Argo CD reads it without a password)
   - **Do NOT** tick "Add a README" — leave it empty → **Create repository**
3. Create a Personal Access Token (you'll use it instead of your password when pushing code):
   - Profile picture → **Settings** → **Developer settings** (bottom of left menu) → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
   - Note: `cno-project` · Expiration: 30 days
   - Tick **`repo`** and **`workflow`** → **Generate token**
   - **Copy the token and save it in Notes** — GitHub shows it only once. Never share it with anyone.

---

## Part 2 — Create your AWS account (15 min)

1. Go to **https://aws.amazon.com** → **Create an AWS account**.
2. Enter email + account name, verify the email code, set a root password.
3. **Account plan:** choose **Paid plan**. You still get the sign-up credits; the Free plan can block EKS.
4. Enter your address and a **debit/credit card**. AWS charges ₹2 to verify it.
   - If the card is rejected, enable **international / online transactions** in your bank app and try again.
5. Verify your phone (SMS/call) → Support plan: **Basic (free)** → finish.
6. Log in to the **AWS Console** as root user.
7. Top-right region selector → choose **Asia Pacific (Mumbai) ap-south-1**. Keep this region for everything.

### 2a. Set a budget alert (2 min — strongly recommended)
Search **Budgets** → **Create budget** → **Use a template** → **Monthly cost budget** → amount **10** (USD) → your email → **Create budget**.

### 2b. Create an IAM user and access keys
Using the root account for daily work is unsafe, so create an admin user for this project:

1. Search **IAM** → **Users** → **Create user**
2. User name: `cno-admin` → **Next**
3. **Attach policies directly** → tick **AdministratorAccess** → **Next** → **Create user**
4. Click `cno-admin` → **Security credentials** tab → **Create access key**
5. Use case: **Command Line Interface (CLI)** → tick the confirmation → **Next** → **Create access key**
6. Click **Download .csv file**. It has your **Access key ID** and **Secret access key**. Never share these or put them in GitHub.

---

## Part 3 — Launch the EC2 workstation (10 min)

All commands run on a small Linux machine in AWS, so you don't need to install anything on your Mac.

1. Search **EC2** → **Launch instance**
2. Name: `eventpass-workstation`
3. AMI: **Ubuntu Server 24.04 LTS** (64-bit **x86**, not Arm)
4. Instance type: **t3.small**
5. Key pair → **Create new key pair** → name `eventpass-key`, type RSA, format **.pem** → **Create**. It downloads to your **Downloads** folder.
6. Network settings: keep **Allow SSH traffic from** → change to **My IP**
7. Storage: **20 GiB**
8. **Launch instance** → open the instance → copy its **Public IPv4 address** (e.g. `13.233.45.67`).

---

## Part 4 — Connect from your Mac (5 min)

Open **Terminal** (press `Cmd + Space`, type *Terminal*, Enter). Replace `YOUR_IP` with the address you copied.

```bash
cd ~/Downloads
chmod 400 eventpass-key.pem
```

Copy the project to EC2. Pick the line that matches what's in your Downloads folder:

```bash
# If you have the file eventpass.zip
scp -i eventpass-key.pem eventpass.zip ubuntu@YOUR_IP:~

# If your Mac already unzipped it into a folder called eventpass
scp -i eventpass-key.pem -r eventpass ubuntu@YOUR_IP:~
```

Log in to EC2 (type `yes` the first time):

```bash
ssh -i eventpass-key.pem ubuntu@YOUR_IP
```

Your prompt now looks like `ubuntu@ip-172-31-...:~$`. **Everything from here runs inside this EC2 terminal.**

---

## Part 5 — Install the tools on EC2 (5 min)

```bash
sudo apt-get update && sudo apt-get install -y unzip
unzip -o eventpass.zip          # skip this line if you copied the folder instead
cd eventpass
bash scripts/setup-ec2.sh
```

The script installs Docker, Git, AWS CLI, kubectl and eksctl and prints their versions (📸 screenshot this).
**Then type `exit` and run the same `ssh -i ...` command again** so Docker works without `sudo`.

Back in EC2:

```bash
cd eventpass
docker ps        # should show an empty table, not "permission denied"
```

---

## Part 6 — Connect the AWS CLI (2 min)

```bash
aws configure
```

| Prompt | Type |
|---|---|
| AWS Access Key ID | from the .csv |
| AWS Secret Access Key | from the .csv |
| Default region name | `ap-south-1` |
| Default output format | `json` |

Check it works:

```bash
aws sts get-caller-identity
```

You should see your 12-digit account number and `user/cno-admin`.

---

## Part 7 — Configure the project (1 min)

```bash
bash scripts/configure.sh
```

It reads your AWS account ID automatically and asks:
- Region → press **Enter** (ap-south-1)
- GitHub username → type yours exactly
- Repository name → press **Enter** (eventpass)

This fills your details into the Kubernetes, Argo CD, IAM and pipeline files.

---

## Part 8 — Create the EKS cluster (~20 min)

```bash
eksctl create cluster -f cluster/cluster.yaml
```

This creates the Kubernetes control plane, a VPC and 2 worker nodes. Wait until you see **`EKS cluster "eventpass-cluster" in "ap-south-1" region is ready`**. If your SSH session drops, reconnect and run `eksctl get cluster --region ap-south-1` to check progress. Don't run the create command again.

```bash
kubectl get nodes
```

Both nodes should be **Ready** (📸).

---

## Part 9 — First deployment: Docker → ECR → EKS (5 min)

```bash
bash scripts/first-deploy.sh
```

This creates the ECR repository, builds the Docker image, pushes it as `v1`, and applies the manifests in `k8s/`. Then get the app's public URL:

```bash
kubectl get svc eventpass-svc -n eventpass
```

Copy the long `EXTERNAL-IP` (ends with `.elb.amazonaws.com`) and open **`http://`** + that address in Safari/Chrome. Give it **2–3 minutes** the first time. Until then the page may not load.

📸 Screenshot the app, `kubectl get all -n eventpass`, and the image in **AWS Console → ECR → eventpass**.

---

## Part 10 — CI/CD with GitHub Actions (10 min)

### 10a. Let GitHub log in to AWS securely (OIDC)

```bash
bash scripts/setup-github-oidc.sh
```

It prints a value like `arn:aws:iam::123456789012:role/github-actions-eventpass`. Copy it, then on GitHub open your **eventpass** repo:

- **Settings → Secrets and variables → Actions → New repository secret**
  - Name: `AWS_ROLE_ARN`
  - Secret: paste the ARN → **Add secret**
- **Settings → Actions → General → Workflow permissions** → **Read and write permissions** → **Save**

### 10b. Push the code to GitHub

Replace `YOUR_USERNAME` and the email:

```bash
git config --global user.name "Pooja Patel"
git config --global user.email "you@example.com"
git config --global credential.helper store      # remembers the token on this EC2

git init
git add .
git commit -m "Initial commit: EventPass"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/eventpass.git
git push -u origin main
```

When asked: **Username** = your GitHub username, **Password** = paste the **token** from Part 1. Nothing shows while you paste; that's normal.

### 10c. Watch the pipeline
GitHub repo → **Actions** tab → the run **"CI/CD - test, build, push to ECR, update manifest"**. Both jobs should turn green ✅ (~3 min).

The pipeline:
1. runs the unit tests,
2. builds a new image tagged with the commit ID and pushes it to ECR,
3. edits `k8s/deployment.yaml` with the new tag and commits it back (you'll see a commit by **github-actions[bot]**).

📸 Screenshot the green run and the ECR repo now holding two images.

---

## Part 11 — GitOps with Argo CD (10 min)

```bash
git pull
bash scripts/install-argocd.sh
```

At the end it prints the **Argo CD UI address, username `admin` and password**. Open `https://` + that address. If it doesn't load yet, wait 2 minutes. Safari/Chrome will warn about the certificate: click **Show Details → visit this website** (Safari) or **Advanced → Proceed** (Chrome). Log in.

You'll see the **eventpass** application. It should become **Synced** and **Healthy** (📸 the app tree view).

```bash
kubectl get applications -n argocd
```

### ⭐ The GitOps demo (do this in the viva)

1. Make a visible change:
   ```bash
   sed -i 's|<h1>Dashboard</h1>|<h1>EventPass Dashboard - v2</h1>|' templates/dashboard.html
   ```
2. Push it:
   ```bash
   git add .
   git commit -m "Update dashboard heading"
   git push
   ```
3. **GitHub → Actions:** the pipeline runs, pushes a new image and commits the new tag.
4. **Argo CD:** within ~3 minutes it shows the new commit and rolls out a new pod. Click **Refresh** to speed it up.
5. Reload the app: the new heading appears, and the footer's **build** and **pod** values change.

> Before each new change, run `git pull` first. The pipeline adds a commit, so your copy must catch up.

**Self-heal demo:** delete the app's pod or scale it by hand. Argo CD puts it back to what Git says:

```bash
kubectl scale deployment eventpass -n eventpass --replicas=0
kubectl get pods -n eventpass -w      # Argo CD brings it back to 1 (Ctrl+C to stop watching)
```

### Using the app in the demo
1. **Events** → open *UI/UX Design Sprint* → book 2 tickets → you land on the ticket page with a code like `EP-XXXXXX`.
2. **Check-in** → type that code → "Welcome …". Type it again → "already checked in" (double entry blocked).
3. **+ New event** → create a small event with capacity **2** → book 2 tickets → the event shows **SOLD OUT** and a third booking is refused.
4. Open a ticket → **Cancel booking** → the seats become available again.
5. **Dashboard** → tickets sold, revenue and check-in rate update.
6. Open `http://<app-url>/health` and `/api/stats` to show the JSON endpoints.

---

## Part 12 — 🧹 Cleanup (do this right after the viva!)

```bash
cd ~/eventpass
bash scripts/cleanup.sh
```

Type `YES`. It deletes the load balancers, the EKS cluster (~10–15 min), the ECR images and the IAM role. Then:

1. **AWS Console → EC2 → Instances** → select `eventpass-workstation` → **Instance state → Terminate**
2. **EC2 → Key pairs** → delete `eventpass-key`
3. **CloudFormation**: make sure no `eksctl-eventpass-cluster-*` stacks remain. Delete any that do.
4. **IAM → Users → cno-admin → Security credentials** → deactivate/delete the access key
5. Next day, check **Billing → Bills** to confirm nothing is still running

Your GitHub repo can stay. It's free and shows your work.

---

## 📸 Screenshot checklist

- [ ] Tool versions after `setup-ec2.sh`
- [ ] `aws sts get-caller-identity`
- [ ] `kubectl get nodes` (2 Ready)
- [ ] EKS cluster in AWS Console (EKS → Clusters)
- [ ] ECR repository with images
- [ ] `kubectl get all -n eventpass`
- [ ] The app running in the browser via the load-balancer URL
- [ ] GitHub Actions green run (both jobs)
- [ ] Commit by github-actions[bot] updating the image tag
- [ ] Argo CD app — Synced & Healthy
- [ ] Before/after of the GitOps change (footer build ID changed)

---

## 🛠 Troubleshooting

| Problem | Fix |
|---|---|
| `Permission denied (publickey)` on ssh | You're not in Downloads, or the key name is wrong. Run `cd ~/Downloads` and check `ls *.pem`. Username must be `ubuntu`. |
| `UNPROTECTED PRIVATE KEY FILE` | Run `chmod 400 eventpass-key.pem` |
| ssh just hangs | Your Wi-Fi IP changed. EC2 → Security groups → edit inbound SSH rule → **My IP** again |
| `docker: permission denied` | You didn't log out after setup. `exit` and ssh again |
| `Unable to locate credentials` | Run `aws configure` again |
| eksctl: `AccessDenied` / service not available | Your account is on the Free plan. Billing → **Upgrade plan** to Paid, then retry |
| eksctl fails half-way | `eksctl delete cluster -f cluster/cluster.yaml --wait`, then create again |
| App URL doesn't open | Wait 3 minutes; use `http://` not `https://`; check `kubectl get pods -n eventpass` is Running |
| Pod `ImagePullBackOff` | The image wasn't pushed. Run `bash scripts/first-deploy.sh` again |
| `git push` asks for password and fails | Paste the **token**, not your GitHub password |
| `git push` rejected (fetch first) | Run `git pull --rebase`, then push again |
| Actions: `Could not assume role` / `Not authorized to perform sts:AssumeRoleWithWebIdentity` | GitHub username/repo typed wrong in Part 7, or the secret is missing. Fix `iam/github-trust-policy.json` and run `bash scripts/setup-github-oidc.sh` again |
| Actions: push of manifest fails (403) | Part 10a → Workflow permissions → **Read and write** |
| Argo CD shows `OutOfSync` / `Unknown` | Repo must be **Public**; click **Refresh** then **Sync** |
| Forgot Argo CD password | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" \| base64 -d; echo` |

---

## 🎤 Likely viva questions

1. **What is cloud-native?** Apps built as containers, managed by an orchestrator (Kubernetes), deployed automatically and able to scale and self-heal.
2. **Docker image vs container?** An image is the read-only template; a container is a running instance of it.
3. **Why ECR?** A private, managed AWS container registry. EKS nodes pull images from it securely inside AWS.
4. **What is EKS?** AWS-managed Kubernetes. AWS runs the control plane (API server, etcd, scheduler); we run worker nodes.
5. **Pod, Deployment, Service?** A Pod runs the container(s); a Deployment keeps the desired number of pods and does rolling updates; a Service gives them a stable address. `type: LoadBalancer` creates an AWS load balancer.
6. **What do the probes do?** Readiness: send traffic only when `/health` responds. Liveness: restart the container if it stops responding.
7. **Why resource requests/limits?** Requests help the scheduler place pods; limits stop one pod using all node CPU/RAM.
8. **What is CI/CD here?** CI = tests + image build on every push; CD = new image pushed to ECR and the manifest updated automatically.
9. **What is OIDC and why not access keys in GitHub?** GitHub gets a short-lived token, and AWS trusts it only for this repo via the IAM role. No long-lived secret can leak.
10. **What is GitOps?** Git is the single source of truth for what runs in the cluster. Argo CD continuously compares the cluster with Git and syncs any difference.
11. **Push vs pull deployment?** The pipeline never touches the cluster. Argo CD *pulls* changes from inside the cluster, so no cluster credentials live in GitHub.
12. **What is self-heal / prune?** Self-heal reverts manual `kubectl` changes; prune deletes resources removed from Git.
13. **Rolling update with `maxUnavailable: 0`?** The new pod must be Ready before the old one is removed, so there's no downtime.
14. **Why 1 replica?** The demo stores data in SQLite inside the pod. For multiple replicas you'd move the data to Amazon RDS. Data also resets when a pod is replaced (`emptyDir`). That's fine for a demo, and RDS or a PersistentVolume fixes it in production.
15. **How would you roll back?** `git revert` the deploy commit; Argo CD syncs the old image. Or roll back from the Argo CD history.
16. **How does the app prevent overbooking?** Before saving a booking it sums the confirmed tickets for that event and rejects the request if the new tickets would exceed capacity. Cancelled bookings aren't counted, which is how cancelling frees seats.

---

## Run locally (optional)

```bash
pip install -r requirements.txt pytest
pytest -v
python app.py      # http://localhost:5000
```
