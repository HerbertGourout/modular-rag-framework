# Cas d'usage business — Modular RAG Framework

> Document interne Publicis Sapient. Audience : management, leads technique, interlocuteurs de projets clients.

---

## Résumé exécutif

Ce framework est un **accélérateur de delivery propriétaire** développé en interne par Publicis Sapient. Il fournit une couche d'orchestration, de gouvernance et de sécurité au-dessus des meilleurs outils open source RAG disponibles — ce que nul framework OSS générique ne propose pour un contexte enterprise. Chaque projet client qui l'utilise économise 4 à 8 semaines de setup. Sur 5 projets par an, le développement complet V1–V4 est amorti.

---

## 1. Actif commercial réutilisable

Ce framework est de l'IP propriétaire qui reste chez Publicis Sapient à chaque fin de projet, contrairement à une implémentation LangChain sur mesure livrée au client.

- **Économie par projet** : 4 à 8 semaines de setup, sécurité, observabilité et gouvernance ne sont plus refaites à zéro.
- **Montée en marge** : les semaines économisées en infrastructure ne sont pas perdues — elles sont réaffectées à de la valeur business facturable.
- **Pricing premium** : un framework propriétaire justifie des day rates plus élevés que "on utilise LangChain comme tout le monde".
- **Compounding** : chaque adapter, manifest ou policy construits sur un projet s'accumulent dans le framework. L'actif s'apprécie à chaque livraison.

---

## 2. Accélérateur de delivery

Le manifest YAML est la clé : configurer un pipeline RAG complet — chunker, embedder, retriever hybride, reranker, LLM, sécurité — se fait en quelques heures, pas en semaines.

- **Prototype démontrable en 1 jour** : pour un appel d'offres ou une discovery, montrer un pipeline fonctionnel sur les documents du client en 24 heures est un argument de vente immédiat.
- **Onboarding accéléré** : un nouveau consultant sur le projet comprend l'architecture en une demi-journée — pas besoin de décoder une codebase LangChain non structurée.
- **Staffing flexible** : l'architecture hexagonale standardisée permet d'interchanger les équipes entre projets sans longue période d'adaptation.
- **Configuration sans code** : un lead ou un PM peut lire et modifier un manifest YAML sans ouvrir Python.

---

## 3. Différenciation concurrentielle

Les concurrents (Accenture, Capgemini, Deloitte Digital) utilisent LangChain, LlamaIndex, ou des solutions propriétaires cloud. Publicis Sapient peut se positionner différemment.

- **"Nous avons notre propre framework RAG enterprise"** : accroche de pitch que peu de cabinets peuvent tenir de façon crédible et démontrable.
- **Gouvernance by design** : la V4 avec policies multi-tenant, audit trail et isolation des données n'existe dans aucun framework OSS. C'est un argument décisif sur les appels d'offres régulés.
- **Architecture démontrable** : les ADRs, les contrats Pydantic, et la structure hexagonale sont des preuves de maturité technique montrables à un DSI ou un RSSI lors d'un audit.
- **Indépendance des vendors** : l'adapter pattern prouve que Publicis Sapient ne revend pas simplement OpenAI ou AWS — elle apporte une couche de valeur propre, neutre, et pérenne.

---

## 4. Couverture des industries régulées

Publicis Sapient travaille avec des banques, des assureurs, des acteurs pharmaceutiques, des utilities — tous soumis à des réglementations strictes (RGPD, DORA, NIS2, sectorielles). Ce framework adresse ces contraintes directement.

- **Audit trail complet** : chaque retrieval, génération et décision de sécurité est tracée dans la `Trace`. Un DPO peut retracer une réponse à son contexte exact.
- **Redaction PII automatique** : emails, téléphones, IBANs, clés API supprimés avant exposition — documentable dans un DPIA.
- **Isolation multi-tenant** : chaque client ou business unit dispose de ses propres policies et de ses propres données, sans risque de cross-contamination.
- **Safety vs Security explicitement séparés** : distinction que les régulateurs apprécient, et qui prouve que la sécurité n'est pas une afterthought.

---

## 5. Résilience face à l'évolution du marché IA

Le marché des LLMs change tous les six mois. Ce framework est conçu pour survivre à ces changements sans réécriture.

- **Swapper un LLM en une ligne YAML** : quand GPT-5 sort ou qu'un client impose Mistral on-premise, le changement ne touche pas au pipeline.
- **Intégrer les meilleurs outils OSS à tout moment** : LlamaIndex pour le chunking sémantique, Ragas pour l'évaluation, LiteLLM comme gateway — tous wrappables en adapters de 50 lignes. Le framework orchestre, il ne réinvente pas.
- **Pas de dépendance à une startup externe** : LangChain a failli disparaître, LlamaIndex change son API régulièrement. Ici, Publicis Sapient contrôle ses propres contrats.
- **Déploiement on-premise possible** : avec HuggingFace + Qdrant, le framework tourne entièrement sans appel à des APIs externes — exigence fréquente dans les projets à données sensibles.

---

## 6. Fondation pour une offre de service structurée

Ce framework peut être le socle d'une practice AI formalisée et répétable.

- **RAG-as-a-Service** : packager le framework + hosting + support comme une offre vendue à des clients qui ne veulent pas gérer l'infrastructure.
- **Audit de systèmes RAG existants** : la connaissance du framework permet d'auditer des implémentations tierces chez des clients qui ont commencé avec LangChain.
- **Formation interne** : créer un cursus "RAG Engineer PS" basé sur ce framework — compétence différenciante sur le marché du recrutement et de la rétention.
- **Transfert de compétences client** : dans certains contextes, livrer le framework comme fondation que le client maintient ensuite — modèle de licensing ou de transfert.

---

## 7. Attractivité et rétention des talents

Les ingénieurs seniors choisissent leurs employeurs en partie sur la qualité technique des projets internes.

- **"Chez PS on construit nos propres outils"** est un argument de recrutement face à des cabinets qui n'assemblent que des SaaS.
- Un framework potentiellement open-sourcé générerait de la visibilité publique, des contributions externes, et des candidatures entrantes.
- Les contributeurs internes développent une expertise RAG architecture rare sur le marché — compétence valorisable en mission client.

---

## 8. Valorisation de la connaissance métier accumulée

Publicis Sapient accumule une expertise méthodologique sur des dizaines de projets. Ce framework est le véhicule pour capitaliser cette connaissance.

- Les patterns découverts sur un projet (chunking optimal pour des documents juridiques, stratégie de reranking pour des FAQ produits) sont encodés en adapters et manifests réutilisables.
- Les évaluations Ragas d'un projet alimentent les benchmarks du suivant.
- Le Graph Memory (V3) peut modéliser la connaissance sectorielle accumulée — un actif qui s'apprécie dans le temps.

---

## 9. Positionnement sur les projets à fort enjeu

Certains projets nécessitent des garanties que les frameworks OSS ne peuvent pas fournir.

- **Souveraineté des données** : déploiement entièrement on-premise ou cloud privé client, sans appel à des APIs externes.
- **Explicabilité** : les citations sourcées, les scores de groundedness, et la trace complète permettent de justifier chaque réponse — exigence fréquente dans les projets de décision assistée.
- **SLAs définissables** : la télémétrie OpenTelemetry permet de mesurer la latence, les tokens, les coûts à chaque étape — et donc de s'engager sur des SLAs contractuels.
- **Clients grands comptes** : les interlocuteurs DSI et RSSI des grandes entreprises veulent de la gouvernance, de l'auditabilité, et de la maîtrise. Ce framework leur parle directement.

---

## Synthèse

| Dimension | Bénéfice direct |
|---|---|
| IP réutilisable | Marges supérieures sur chaque projet client |
| Delivery accéléré | 4–8 semaines économisées par projet |
| Différenciation | Pitch gagnant sur les appels d'offres régulés |
| Gouvernance | Conformité RGPD/DORA démontrable |
| Résilience | Zéro lock-in vendor, compatible avec toute évolution LLM |
| Offre de service | Base d'une practice RAG enterprise formalisée |
| Talent | Recrutement et rétention des profils AI seniors |
| Connaissance | Capitalisation cross-projets, actif qui s'apprécie |
| Projets critiques | SLAs, souveraineté, explicabilité sur grands comptes |

Ce framework transforme chaque projet RAG de Publicis Sapient d'un coût en un investissement. La vraie question n'est pas "est-ce que ça vaut le coup" — c'est "combien de projets faut-il pour que ça soit rentable". La réponse : un ou deux projets clients suffisent à amortir le développement complet V1–V4.
