"""WeChatAgent whitelist & contact management CLI."""
import argparse
import sys
from pathlib import Path

from src.core.context import ContextManager
from src.models.schemas import Contact


DB_PATH = Path("data/agent.db")


def add_contact(args):
    ctx = ContextManager(DB_PATH)
    contact = Contact(
        wxid=args.wxid,
        nickname=args.nickname,
        relationship=args.relationship or "朋友",
        is_whitelist=True,
    )
    ctx.save_contact(contact)
    print(f"已添加白名单联系人: {args.nickname} ({args.wxid})")
    ctx.close()


def remove_contact(args):
    ctx = ContextManager(DB_PATH)
    contact = ctx.get_contact(args.wxid)
    if not contact:
        print(f"未找到联系人: {args.wxid}")
        ctx.close()
        return
    contact.is_whitelist = False
    ctx.save_contact(contact)
    print(f"已从白名单移除: {contact.nickname or args.wxid}")
    ctx.close()


def list_contacts(args):
    ctx = ContextManager(DB_PATH)
    contacts = ctx.get_whitelist_contacts()
    if not contacts:
        print("白名单为空")
    else:
        print(f"白名单联系人 ({len(contacts)}):")
        for c in contacts:
            status = "暂停" if c.is_paused else "活跃"
            print(f"  - {c.nickname or '?'} ({c.wxid}) [{status}]")
    ctx.close()


def main():
    parser = argparse.ArgumentParser(description="WeChatAgent 管理工具")
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="添加白名单联系人")
    add_p.add_argument("wxid", help="微信ID或备注名（通知中显示的名字）")
    add_p.add_argument("nickname", help="昵称")
    add_p.add_argument("-r", "--relationship", help="关系描述，如：女朋友、同事、老妈")
    add_p.set_defaults(func=add_contact)

    rm_p = sub.add_parser("remove", help="从白名单移除")
    rm_p.add_argument("wxid", help="微信ID")
    rm_p.set_defaults(func=remove_contact)

    ls_p = sub.add_parser("list", help="查看白名单")
    ls_p.set_defaults(func=list_contacts)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
