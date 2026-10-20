import argparse
from .data import load_config, download_target, prepare_source, prepare_target


def main():
    parser = argparse.ArgumentParser(description='AirePredict: preparación y evaluación temporal')
    parser.add_argument('stage', choices=['download', 'prepare', 'experiment', 'serve', 'ingest', 'readiness', 'registry-init', 'registry-status', 'retrain', 'rollback', 'monitor', 'mlops-demo', 'maintenance'])
    parser.add_argument('--refresh', action='store_true', help='Actualizar copias del archivo público')
    args = parser.parse_args()
    if args.stage in ['registry-init', 'registry-status', 'retrain', 'rollback', 'monitor', 'mlops-demo', 'maintenance']:
        import json
        from .registry import Registry, initialize
        from .maintenance import run, demo
        from .monitoring import monitor
        registry = Registry()
        try:
            if args.stage == 'registry-init':
                result = {'active': initialize(registry), 'status': 'experimental'}
            elif args.stage == 'registry-status':
                result = {'state': registry.state(), 'history': registry.history()}
            elif args.stage == 'rollback':
                result = {'restored': registry.rollback(reason='Operator requested rollback')}
            elif args.stage == 'retrain':
                result = run(registry)
            elif args.stage == 'monitor':
                result = monitor(registry)
            elif args.stage == 'maintenance':
                from .live import ingest
                active = initialize(registry)
                try:
                    result = {'ingestion': ingest(), 'retraining': run(registry), 'monitoring': monitor(registry)}
                except Exception as exc:
                    registry.event('maintenance_failed', active, {'error_type': type(exc).__name__, 'message': str(exc), 'active_after_failure': registry.state()['active']})
                    raise
            else:
                report = demo()
                result = {'historical_simulation': True, 'application_registry_modified': False,
                          'first_training': report['first_training']['status'], 'repeated_training': report['repeated_training']['status'],
                          'rollback_restored_baseline': report['restored'] == report['initial_baseline'],
                          'report': 'reports/mlops_demo.json'}
        except Exception as exc:
            parser.exit(2, f'{type(exc).__name__}: {exc}\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.stage == 'serve':
        import os
        import uvicorn
        uvicorn.run('airepredict.service:app', host=os.environ.get('AIRPREDICT_HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '8000')))
        return
    if args.stage in ['ingest', 'readiness']:
        import json
        from .live import ingest, retraining_readiness
        try:
            result = ingest() if args.stage == 'ingest' else retraining_readiness()
        except RuntimeError as exc:
            parser.exit(2, str(exc)+'\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    config = load_config()
    manifest = download_target(config, refresh=args.refresh)
    if args.stage == 'download':
        return
    source, source_stats = prepare_source(config)
    target, target_stats = prepare_target(config, manifest)
    if args.stage == 'experiment':
        from .experiment import run
        run(config, source, target, source_stats, target_stats, manifest)


if __name__ == '__main__':
    main()
