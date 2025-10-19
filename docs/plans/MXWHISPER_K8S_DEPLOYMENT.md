# MxWhisper Kubernetes Deployment Plan

## Overview
Deployment strategy for MxWhisper knowledge base system on RKE2 Kubernetes cluster with Ceph storage.

## Infrastructure Context

**Cluster**: RKE2 Kubernetes
**Namespace**: `ai-services`
**Storage**: Ceph RBD (`ceph-rbd-fast`)
**Ingress**: NGINX
**Domain**: `mixwarecs-home.net`
**Deployment Tool**: Ansible playbooks

---

## System Components

### 1. PostgreSQL Database (StatefulSet)
- **Purpose**: Primary data store for jobs, users, chunks, embeddings
- **Storage**: 100Gi PVC (Ceph RBD)
- **Replicas**: 1 (can scale to 3 with Patroni for HA)

### 2. Redis Cache (Deployment)
- **Purpose**: Session cache, job queues, rate limiting
- **Storage**: 10Gi PVC
- **Replicas**: 1 (can use Redis Sentinel for HA)

### 3. Temporal Server (Deployment)
- **Purpose**: Workflow orchestration for transcription pipeline
- **Replicas**: 1
- **Dependencies**: PostgreSQL (for Temporal state)

### 4. MxWhisper API (Deployment)
- **Purpose**: FastAPI REST API server
- **Storage**: 200Gi PVC (audio files, transcripts, models)
- **Replicas**: 2-3 (horizontal scaling)
- **Resources**: 4 CPU, 8Gi RAM per pod

### 5. MxWhisper Temporal Workers (Deployment)
- **Purpose**: Process transcription, chunking, embedding, categorization
- **Replicas**: 3-5 (auto-scale based on queue depth)
- **Resources**: 8 CPU, 16Gi RAM per pod (CPU-intensive)
- **GPU**: Optional (if using GPU-accelerated Whisper)

### 6. MxWhisper MCP Server (Deployment)
- **Purpose**: MCP interface for knowledge base access
- **Replicas**: 2 (HA)
- **Mode**: HTTP (for n8n and external access)

---

## Ansible Playbook Structure

### File: `rke2/playbooks/ai-services/05-deploy-mxwhisper.yml`

```yaml
---
- name: Deploy MxWhisper Knowledge Base System
  hosts: localhost
  gather_facts: true
  vars:
    kubeconfig_path: "{{ ansible_env.KUBECONFIG }}"
    namespace: "ai-services"

    # Images
    mxwhisper_api_image: "harbor.mixwarecs-home.net/mxwhisper/api:latest"
    mxwhisper_worker_image: "harbor.mixwarecs-home.net/mxwhisper/worker:latest"
    mxwhisper_mcp_image: "harbor.mixwarecs-home.net/mxwhisper/mcp:latest"
    postgres_image: "docker.io/postgres:16-alpine"
    redis_image: "docker.io/redis:7-alpine"
    temporal_image: "docker.io/temporalio/auto-setup:1.22.0"

    # Storage
    storage_class: "ceph-rbd-fast"
    db_storage_size: "100Gi"
    media_storage_size: "200Gi"
    redis_storage_size: "10Gi"

    # Ingress
    api_ingress_host: "mxwhisper.mixwarecs-home.net"
    mcp_ingress_host: "mxwhisper-mcp.mixwarecs-home.net"

    # Scaling
    api_replicas: 2
    worker_replicas: 3
    mcp_replicas: 2

  tasks:
    # ============================================================
    # Phase 1: Secrets
    # ============================================================
    - name: Create MxWhisper secrets
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Secret
          metadata:
            name: mxwhisper-secrets
            namespace: "{{ namespace }}"
          type: Opaque
          stringData:
            postgres_password: "{{ lookup('password', '/dev/null length=32 chars=ascii_letters,digits') }}"
            jwt_secret: "{{ lookup('password', '/dev/null length=64 chars=ascii_letters,digits') }}"
            api_key: "{{ lookup('password', '/dev/null length=32 chars=ascii_letters,digits') }}"
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 2: Persistent Storage
    # ============================================================
    - name: Create PostgreSQL PVC
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: PersistentVolumeClaim
          metadata:
            name: mxwhisper-postgres-data
            namespace: "{{ namespace }}"
          spec:
            accessModes: ["ReadWriteOnce"]
            resources:
              requests:
                storage: "{{ db_storage_size }}"
            storageClassName: "{{ storage_class }}"
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create media storage PVC
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: PersistentVolumeClaim
          metadata:
            name: mxwhisper-media
            namespace: "{{ namespace }}"
          spec:
            accessModes: ["ReadWriteMany"]  # Shared across API/workers
            resources:
              requests:
                storage: "{{ media_storage_size }}"
            storageClassName: "{{ storage_class }}"
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create Redis PVC
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: PersistentVolumeClaim
          metadata:
            name: mxwhisper-redis-data
            namespace: "{{ namespace }}"
          spec:
            accessModes: ["ReadWriteOnce"]
            resources:
              requests:
                storage: "{{ redis_storage_size }}"
            storageClassName: "{{ storage_class }}"
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 3: PostgreSQL Database
    # ============================================================
    - name: Deploy PostgreSQL StatefulSet
      kubernetes.core.k8s:
        definition:
          apiVersion: apps/v1
          kind: StatefulSet
          metadata:
            name: mxwhisper-postgres
            namespace: "{{ namespace }}"
          spec:
            serviceName: mxwhisper-postgres
            replicas: 1
            selector:
              matchLabels:
                app: mxwhisper-postgres
            template:
              metadata:
                labels:
                  app: mxwhisper-postgres
              spec:
                containers:
                  - name: postgres
                    image: "{{ postgres_image }}"
                    ports:
                      - containerPort: 5432
                    env:
                      - name: POSTGRES_DB
                        value: "mxwhisper"
                      - name: POSTGRES_USER
                        value: "mxwhisper"
                      - name: POSTGRES_PASSWORD
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: postgres_password
                      - name: PGDATA
                        value: /var/lib/postgresql/data/pgdata
                    volumeMounts:
                      - name: postgres-data
                        mountPath: /var/lib/postgresql/data
                    resources:
                      requests:
                        memory: "2Gi"
                        cpu: "1"
                      limits:
                        memory: "4Gi"
                        cpu: "2"
                volumes:
                  - name: postgres-data
                    persistentVolumeClaim:
                      claimName: mxwhisper-postgres-data
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create PostgreSQL Service
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Service
          metadata:
            name: mxwhisper-postgres
            namespace: "{{ namespace }}"
          spec:
            selector:
              app: mxwhisper-postgres
            ports:
              - port: 5432
                targetPort: 5432
            clusterIP: None  # Headless service for StatefulSet
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 4: Redis Cache
    # ============================================================
    - name: Deploy Redis
      kubernetes.core.k8s:
        definition:
          apiVersion: apps/v1
          kind: Deployment
          metadata:
            name: mxwhisper-redis
            namespace: "{{ namespace }}"
          spec:
            replicas: 1
            selector:
              matchLabels:
                app: mxwhisper-redis
            template:
              metadata:
                labels:
                  app: mxwhisper-redis
              spec:
                containers:
                  - name: redis
                    image: "{{ redis_image }}"
                    ports:
                      - containerPort: 6379
                    volumeMounts:
                      - name: redis-data
                        mountPath: /data
                    resources:
                      requests:
                        memory: "512Mi"
                        cpu: "500m"
                      limits:
                        memory: "2Gi"
                        cpu: "1"
                volumes:
                  - name: redis-data
                    persistentVolumeClaim:
                      claimName: mxwhisper-redis-data
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create Redis Service
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Service
          metadata:
            name: mxwhisper-redis
            namespace: "{{ namespace }}"
          spec:
            selector:
              app: mxwhisper-redis
            ports:
              - port: 6379
                targetPort: 6379
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 5: Temporal Server
    # ============================================================
    - name: Deploy Temporal Server
      kubernetes.core.k8s:
        definition:
          apiVersion: apps/v1
          kind: Deployment
          metadata:
            name: mxwhisper-temporal
            namespace: "{{ namespace }}"
          spec:
            replicas: 1
            selector:
              matchLabels:
                app: mxwhisper-temporal
            template:
              metadata:
                labels:
                  app: mxwhisper-temporal
              spec:
                containers:
                  - name: temporal
                    image: "{{ temporal_image }}"
                    ports:
                      - containerPort: 7233
                    env:
                      - name: DB
                        value: "postgresql"
                      - name: DB_PORT
                        value: "5432"
                      - name: POSTGRES_SEEDS
                        value: "mxwhisper-postgres"
                      - name: POSTGRES_USER
                        value: "mxwhisper"
                      - name: POSTGRES_PWD
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: postgres_password
                    resources:
                      requests:
                        memory: "1Gi"
                        cpu: "500m"
                      limits:
                        memory: "2Gi"
                        cpu: "1"
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create Temporal Service
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Service
          metadata:
            name: mxwhisper-temporal
            namespace: "{{ namespace }}"
          spec:
            selector:
              app: mxwhisper-temporal
            ports:
              - port: 7233
                targetPort: 7233
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 6: MxWhisper API
    # ============================================================
    - name: Deploy MxWhisper API
      kubernetes.core.k8s:
        definition:
          apiVersion: apps/v1
          kind: Deployment
          metadata:
            name: mxwhisper-api
            namespace: "{{ namespace }}"
          spec:
            replicas: "{{ api_replicas }}"
            selector:
              matchLabels:
                app: mxwhisper-api
            template:
              metadata:
                labels:
                  app: mxwhisper-api
              spec:
                containers:
                  - name: api
                    image: "{{ mxwhisper_api_image }}"
                    ports:
                      - containerPort: 8000
                    env:
                      - name: DATABASE_URL
                        value: "postgresql://mxwhisper:$(POSTGRES_PASSWORD)@mxwhisper-postgres:5432/mxwhisper"
                      - name: POSTGRES_PASSWORD
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: postgres_password
                      - name: REDIS_URL
                        value: "redis://mxwhisper-redis:6379/0"
                      - name: TEMPORAL_HOST
                        value: "mxwhisper-temporal:7233"
                      - name: JWT_SECRET
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: jwt_secret
                      - name: MEDIA_PATH
                        value: "/media"
                    volumeMounts:
                      - name: media
                        mountPath: /media
                    resources:
                      requests:
                        memory: "4Gi"
                        cpu: "2"
                      limits:
                        memory: "8Gi"
                        cpu: "4"
                    livenessProbe:
                      httpGet:
                        path: /health
                        port: 8000
                      initialDelaySeconds: 30
                      periodSeconds: 10
                    readinessProbe:
                      httpGet:
                        path: /health
                        port: 8000
                      initialDelaySeconds: 10
                      periodSeconds: 5
                volumes:
                  - name: media
                    persistentVolumeClaim:
                      claimName: mxwhisper-media
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create MxWhisper API Service
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Service
          metadata:
            name: mxwhisper-api
            namespace: "{{ namespace }}"
          spec:
            selector:
              app: mxwhisper-api
            ports:
              - port: 8000
                targetPort: 8000
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create MxWhisper API Ingress
      kubernetes.core.k8s:
        definition:
          apiVersion: networking.k8s.io/v1
          kind: Ingress
          metadata:
            name: mxwhisper-api
            namespace: "{{ namespace }}"
            annotations:
              kubernetes.io/ingress.class: nginx
              nginx.ingress.kubernetes.io/proxy-body-size: "500m"  # Large file uploads
          spec:
            rules:
              - host: "{{ api_ingress_host }}"
                http:
                  paths:
                    - path: /
                      pathType: Prefix
                      backend:
                        service:
                          name: mxwhisper-api
                          port:
                            number: 8000
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 7: Temporal Workers
    # ============================================================
    - name: Deploy MxWhisper Workers
      kubernetes.core.k8s:
        definition:
          apiVersion: apps/v1
          kind: Deployment
          metadata:
            name: mxwhisper-worker
            namespace: "{{ namespace }}"
          spec:
            replicas: "{{ worker_replicas }}"
            selector:
              matchLabels:
                app: mxwhisper-worker
            template:
              metadata:
                labels:
                  app: mxwhisper-worker
              spec:
                containers:
                  - name: worker
                    image: "{{ mxwhisper_worker_image }}"
                    env:
                      - name: DATABASE_URL
                        value: "postgresql://mxwhisper:$(POSTGRES_PASSWORD)@mxwhisper-postgres:5432/mxwhisper"
                      - name: POSTGRES_PASSWORD
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: postgres_password
                      - name: REDIS_URL
                        value: "redis://mxwhisper-redis:6379/0"
                      - name: TEMPORAL_HOST
                        value: "mxwhisper-temporal:7233"
                      - name: MEDIA_PATH
                        value: "/media"
                      - name: WORKER_CONCURRENCY
                        value: "4"
                    volumeMounts:
                      - name: media
                        mountPath: /media
                    resources:
                      requests:
                        memory: "8Gi"
                        cpu: "4"
                      limits:
                        memory: "16Gi"
                        cpu: "8"
                volumes:
                  - name: media
                    persistentVolumeClaim:
                      claimName: mxwhisper-media
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 8: MCP Server (HTTP Mode)
    # ============================================================
    - name: Deploy MxWhisper MCP Server
      kubernetes.core.k8s:
        definition:
          apiVersion: apps/v1
          kind: Deployment
          metadata:
            name: mxwhisper-mcp
            namespace: "{{ namespace }}"
          spec:
            replicas: "{{ mcp_replicas }}"
            selector:
              matchLabels:
                app: mxwhisper-mcp
            template:
              metadata:
                labels:
                  app: mxwhisper-mcp
              spec:
                containers:
                  - name: mcp
                    image: "{{ mxwhisper_mcp_image }}"
                    ports:
                      - containerPort: 3000
                    env:
                      - name: MCP_TRANSPORT
                        value: "http"
                      - name: MCP_ONLY
                        value: "false"  # Enable REST API
                      - name: MCP_PORT
                        value: "3000"
                      - name: MXWHISPER_API_URL
                        value: "http://mxwhisper-api:8000"
                      - name: MXWHISPER_API_KEY
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: api_key
                    resources:
                      requests:
                        memory: "512Mi"
                        cpu: "500m"
                      limits:
                        memory: "1Gi"
                        cpu: "1"
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create MxWhisper MCP Service
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Service
          metadata:
            name: mxwhisper-mcp
            namespace: "{{ namespace }}"
          spec:
            selector:
              app: mxwhisper-mcp
            ports:
              - port: 3000
                targetPort: 3000
        kubeconfig: "{{ kubeconfig_path }}"

    - name: Create MxWhisper MCP Ingress
      kubernetes.core.k8s:
        definition:
          apiVersion: networking.k8s.io/v1
          kind: Ingress
          metadata:
            name: mxwhisper-mcp
            namespace: "{{ namespace }}"
            annotations:
              kubernetes.io/ingress.class: nginx
          spec:
            rules:
              - host: "{{ mcp_ingress_host }}"
                http:
                  paths:
                    - path: /
                      pathType: Prefix
                      backend:
                        service:
                          name: mxwhisper-mcp
                          port:
                            number: 3000
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 9: Database Migrations
    # ============================================================
    - name: Run database migrations
      kubernetes.core.k8s:
        definition:
          apiVersion: batch/v1
          kind: Job
          metadata:
            name: mxwhisper-migrations
            namespace: "{{ namespace }}"
          spec:
            template:
              spec:
                containers:
                  - name: migrations
                    image: "{{ mxwhisper_api_image }}"
                    command: ["alembic", "upgrade", "head"]
                    env:
                      - name: DATABASE_URL
                        value: "postgresql://mxwhisper:$(POSTGRES_PASSWORD)@mxwhisper-postgres:5432/mxwhisper"
                      - name: POSTGRES_PASSWORD
                        valueFrom:
                          secretKeyRef:
                            name: mxwhisper-secrets
                            key: postgres_password
                restartPolicy: OnFailure
            backoffLimit: 3
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 10: Validation
    # ============================================================
    - name: Wait for API deployment
      kubernetes.core.k8s_info:
        api_version: apps/v1
        kind: Deployment
        name: mxwhisper-api
        namespace: "{{ namespace }}"
        kubeconfig: "{{ kubeconfig_path }}"
        wait: true
        wait_condition:
          type: Available
          status: "True"
        wait_timeout: 300

    - name: Test MxWhisper health
      kubernetes.core.k8s:
        definition:
          apiVersion: batch/v1
          kind: Job
          metadata:
            name: mxwhisper-health-test
            namespace: "{{ namespace }}"
          spec:
            ttlSecondsAfterFinished: 120
            template:
              spec:
                containers:
                  - name: curl
                    image: curlimages/curl:latest
                    command:
                      - sh
                      - -c
                      - |
                        echo "Testing MxWhisper API..."
                        curl -f http://mxwhisper-api:8000/health || exit 1
                        echo "Testing MCP Server..."
                        curl -f http://mxwhisper-mcp:3000/health || exit 1
                restartPolicy: Never
            backoffLimit: 2
        kubeconfig: "{{ kubeconfig_path }}"

    # ============================================================
    # Phase 11: Deployment Summary
    # ============================================================
    - name: Display deployment summary
      debug:
        msg: |
          ================== MxWhisper Deployment Summary ==================
          ✅ Status: DEPLOYED

          🌐 Endpoints:
            - API: http://{{ api_ingress_host }}
            - MCP: http://{{ mcp_ingress_host }}

          🔧 Internal Services:
            - API: mxwhisper-api.{{ namespace }}.svc.cluster.local:8000
            - MCP: mxwhisper-mcp.{{ namespace }}.svc.cluster.local:3000
            - PostgreSQL: mxwhisper-postgres.{{ namespace }}.svc.cluster.local:5432
            - Redis: mxwhisper-redis.{{ namespace }}.svc.cluster.local:6379
            - Temporal: mxwhisper-temporal.{{ namespace }}.svc.cluster.local:7233

          📊 Replicas:
            - API: {{ api_replicas }}
            - Workers: {{ worker_replicas }}
            - MCP: {{ mcp_replicas }}

          💾 Storage:
            - PostgreSQL: {{ db_storage_size }}
            - Media: {{ media_storage_size }}
            - Redis: {{ redis_storage_size }}

          🔐 Secrets: mxwhisper-secrets
          ==================================================================
```

---

## Storage Layout

```
Ceph RBD Volumes:
├── mxwhisper-postgres-data (100Gi)
│   └── PostgreSQL database files
│
├── mxwhisper-media (200Gi, ReadWriteMany)
│   ├── uploads/         # Original audio files
│   ├── transcripts/     # Processed transcripts
│   ├── chunks/          # Chunked audio/text
│   └── models/          # Downloaded ML models
│
└── mxwhisper-redis-data (10Gi)
    └── Redis persistence
```

---

## Service Discovery

### Internal DNS Names:

```bash
# API
http://mxwhisper-api.ai-services.svc.cluster.local:8000

# MCP Server (for n8n)
http://mxwhisper-mcp.ai-services.svc.cluster.local:3000

# PostgreSQL
postgresql://mxwhisper-postgres.ai-services.svc.cluster.local:5432/mxwhisper

# Redis
redis://mxwhisper-redis.ai-services.svc.cluster.local:6379

# Temporal
mxwhisper-temporal.ai-services.svc.cluster.local:7233
```

---

## Scaling Strategy

### Horizontal Pod Autoscaler (HPA)

```yaml
# Auto-scale API based on CPU
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: mxwhisper-api-hpa
  namespace: ai-services
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mxwhisper-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

```yaml
# Auto-scale workers based on queue depth
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: mxwhisper-worker-hpa
  namespace: ai-services
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mxwhisper-worker
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80
```

---

## Monitoring & Logging

### Prometheus Metrics

```yaml
# ServiceMonitor for Prometheus Operator
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: mxwhisper
  namespace: ai-services
spec:
  selector:
    matchLabels:
      app: mxwhisper-api
  endpoints:
    - port: http
      path: /metrics
```

### Key Metrics to Monitor:
- API request rate/latency
- Worker queue depth
- Transcription job success/failure rate
- Database connection pool usage
- Storage capacity

---

## Backup Strategy

### Database Backups

```yaml
# CronJob for PostgreSQL backups
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mxwhisper-db-backup
  namespace: ai-services
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16-alpine
              command:
                - sh
                - -c
                - |
                  pg_dump -h mxwhisper-postgres -U mxwhisper mxwhisper | \
                  gzip > /backups/mxwhisper-$(date +%Y%m%d).sql.gz
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: mxwhisper-secrets
                      key: postgres_password
              volumeMounts:
                - name: backups
                  mountPath: /backups
          volumes:
            - name: backups
              persistentVolumeClaim:
                claimName: mxwhisper-backups
          restartPolicy: OnFailure
```

---

## Upgrade Strategy

### Rolling Updates

```bash
# Update API to new version
kubectl set image deployment/mxwhisper-api \
  api=harbor.mixwarecs-home.net/mxwhisper/api:v2.0.0 \
  -n ai-services

# Update workers
kubectl set image deployment/mxwhisper-worker \
  worker=harbor.mixwarecs-home.net/mxwhisper/worker:v2.0.0 \
  -n ai-services

# Update MCP server
kubectl set image deployment/mxwhisper-mcp \
  mcp=harbor.mixwarecs-home.net/mxwhisper/mcp:v2.0.0 \
  -n ai-services
```

### Database Migrations

```bash
# Run migrations before rolling update
kubectl create job --from=cronjob/mxwhisper-migrations \
  mxwhisper-migrate-v2 -n ai-services

# Wait for completion
kubectl wait --for=condition=complete job/mxwhisper-migrate-v2 -n ai-services

# Then proceed with rolling update
```

---

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n ai-services | grep mxwhisper
```

### View Logs
```bash
# API logs
kubectl logs -f deployment/mxwhisper-api -n ai-services

# Worker logs
kubectl logs -f deployment/mxwhisper-worker -n ai-services

# Database logs
kubectl logs -f statefulset/mxwhisper-postgres -n ai-services
```

### Exec into Pod
```bash
kubectl exec -it deployment/mxwhisper-api -n ai-services -- /bin/bash
```

### Check Storage
```bash
kubectl get pvc -n ai-services | grep mxwhisper
```

---

## Security Considerations

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mxwhisper-network-policy
  namespace: ai-services
spec:
  podSelector:
    matchLabels:
      app: mxwhisper-api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: nginx-ingress
      ports:
        - protocol: TCP
          port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: mxwhisper-postgres
      ports:
        - protocol: TCP
          port: 5432
    - to:
        - podSelector:
            matchLabels:
              app: mxwhisper-redis
      ports:
        - protocol: TCP
          port: 6379
```

---

## Next Steps

1. ✅ Deploy MxWhisper using Ansible playbook
2. ✅ Verify all pods are running
3. ✅ Test API endpoints
4. ✅ Test MCP server from n8n
5. ✅ Configure monitoring/alerting
6. ✅ Set up automated backups
7. ✅ Configure HPA for auto-scaling

---

**Deployment Command:**
```bash
cd /home/geo/develop/rke2/playbooks/ai-services
ansible-playbook 05-deploy-mxwhisper.yml
```
