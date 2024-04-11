import argparse
import asyncio
from node.storage.hub.hub import Hub
from node.storage.db.db import DB


async def creds(db, hub):
    user = await hub.get_user(hub.user_id)
    print(user["credits"])


async def coworkers(db, hub):
    coworkers = await hub.list_nodes()
    for coworker in coworkers:
        print(coworker)


async def coops(db, hub):
    modules = await hub.list_modules()
    for module in modules:
        print(module)


async def plans(db, hub):
    plans = await hub.list_plans()
    for plan in plans:
        print(plan)


async def services(db, hub):
    services = await hub.list_services()
    for service in services:
        print(service)


async def tasks(db, hub, task_id):
    tasks = await db.list_tasks(task_id)
    for task in tasks:
        print(task)


async def main():
    db = await DB("seller1", "great-password")
    hub = await Hub("seller1", "great-password")

    parser = argparse.ArgumentParser(
        description="CLI with 'auctions' and 'run' commands"
    )
    subparsers = parser.add_subparsers(title="commands", dest="command")

    coworkers_parser = subparsers.add_parser(
        "coworkers", help="List available Coworker Nodes."
    )
    coops_parser = subparsers.add_parser("coops", help="List available Co-Ops.")
    plans_parser = subparsers.add_parser("plans", help="List current plans.")
    services_parser = subparsers.add_parser("services", help="List available services.")
    tasks_parser = subparsers.add_parser("tasks", help="List tasks.")
    tasks_parser.add_argument("--id", help="Task ID")
    credits_parser = subparsers.add_parser("credits", help="Show available credits.")

    args = parser.parse_args()

    if args.command == "coworkers":
        await coworkers(db, hub)
    elif args.command == "services":
        await services(db, hub)
    elif args.command == "plans":
        await plans(db, hub)
    elif args.command == "tasks":
        await tasks(db, hub, args.id)
    elif args.command == "coops":
        await coops(db, hub)
    elif args.command == "credits":
        await creds(db, hub)
    else:
        parser.print_help()


def cli():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
