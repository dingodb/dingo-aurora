from __future__ import annotations

from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.chart.models import RepoInfo, ChartInfo, AppInfo, TagInfo
from dingo_command.utils.helm.util import ChartLOG as Log
from sqlalchemy import delete

repo_dir_dic= {"create_time":RepoInfo.create_time, "name":RepoInfo.name, "status":RepoInfo.status}
chart_dir_dic= {"repo_name":ChartInfo.repo_name, "name":ChartInfo.name, "tag_name":ChartInfo.tag_name,
                "type": ChartInfo.type, "cluster_id": ChartInfo.cluster_id, "create_time":ChartInfo.create_time,
                "version": ChartInfo.version}
app_dir_dic= {"create_time":AppInfo.create_time, "name":AppInfo.name, "status":AppInfo.status}
tag_dir_dic= {"name":TagInfo.name, "type":TagInfo.type}

class RepoSQL:

    @classmethod
    def list_repos(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 根据query_params查询数据
            query = session.query(RepoInfo)

            # 数据库查询参数
            if "id" in query_params and query_params["id"]:
                query = query.filter(RepoInfo.id == query_params["id"])
            if "cluster_id" in query_params and query_params["cluster_id"]:
                # query = query.filter(RepoInfo.cluster_id == query_params["cluster_id"])
                cluster_ids = [query_params["cluster_id"], "all"]
                query = query.filter(RepoInfo.cluster_id.in_(cluster_ids))
            if "is_global" in query_params:
                query = query.filter(RepoInfo.is_global == query_params["is_global"])
            if "status" in query_params and query_params["status"]:
                query = query.filter(RepoInfo.status == query_params["status"])
            if "name" in query_params and query_params["name"]:
                query = query.filter(RepoInfo.name == query_params["name"])
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in repo_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None :
                    query = query.order_by(repo_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(repo_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(RepoInfo.create_time.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            repo_list = query.all()
            return count, repo_list

    @classmethod
    def create_repo(cls, repo):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(repo)

    @classmethod
    def update_repo(cls, repo):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(repo)

    @classmethod
    def delete_repo_list(cls, repo_list, batch_size=1000):
        if not repo_list:
            return

        session = get_session()
        repo_ids = [repo.id for repo in repo_list]

        try:
            for i in range(0, len(repo_ids), batch_size):
                batch_ids = repo_ids[i:i + batch_size]
                with session.begin():
                    # 1. 删除关联子表（无级联约束时）
                    session.query(ChartInfo).filter(ChartInfo.repo_id.in_(batch_ids)).delete(
                        synchronize_session=False
                    )
                    # 2. 删除主表
                    session.query(RepoInfo).filter(RepoInfo.id.in_(batch_ids)).delete(
                        synchronize_session=False
                    )
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    # @classmethod
    # def delete_repo_list(cls, repo_list):
    #     # Session = sessionmaker(bind=engine, expire_on_commit=False)
    #     # session = Session()
    #     for repo in repo_list:
    #         cls.delete_repo(repo)

    @classmethod
    def delete_repo(cls, repo):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.delete(repo)


class ChartSQL:

    @classmethod
    def list_charts(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 根据query_params查询数据
            query = session.query(ChartInfo)

            # 数据库查询参数
            if "id" in query_params and query_params["id"]:
                query = query.filter(ChartInfo.id == query_params["id"])
            if "cluster_id" in query_params and query_params["cluster_id"]:
                cluster_ids = [query_params["cluster_id"], "all"]
                query = query.filter(ChartInfo.cluster_id.in_(cluster_ids))
            if "name" in query_params and query_params["name"]:
                query = query.filter(ChartInfo.name == query_params["name"])
            if "status" in query_params and query_params["status"]:
                query = query.filter(ChartInfo.status == query_params["status"])
            if "repo_name" in query_params and query_params["repo_name"]:
                query = query.filter(ChartInfo.repo_name == query_params["repo_name"])
            if "repo_id" in query_params and query_params["repo_id"]:
                query = query.filter(ChartInfo.repo_id == query_params["repo_id"])
            if "type" in query_params and query_params["type"]:
                query = query.filter(ChartInfo.type == query_params["type"])
            if "tag_id" in query_params and query_params["tag_id"]:
                query = query.filter(ChartInfo.tag_id == query_params["tag_id"])
            if "tag_name" in query_params and query_params["tag_name"]:
                query = query.filter(ChartInfo.tag_name == query_params["tag_name"])
            if "version" in query_params and query_params["version"]:
                query = query.filter(ChartInfo.version == query_params["version"])
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in chart_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None :
                    query = query.order_by(chart_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(chart_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(ChartInfo.name.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            chart_list = query.all()
            # 返回
            return count, chart_list

    @classmethod
    def create_repo(cls, chart):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(chart)

    @classmethod
    def create_chart_list(cls, chart_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        try:
            with session.begin():
                session.bulk_save_objects(chart_list)
        except Exception as e:
            Log.error("create_chart_list failed, error: %s" % str(e))
            session.rollback()
            raise

    @classmethod
    def update_repo(cls, chart):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(chart)
            
    @classmethod
    def update_chart_list(cls, chart_list):
        session = get_session()
        try:
            with session.begin():
                # 使用bulk_save_objects替代循环merge
                session.bulk_save_objects(chart_list, update_changed_only=True)
        except Exception as e:
            Log.error("update_chart_list failed, error: %s" % str(e))
            session.rollback()
            raise

    @classmethod
    def delete_chart_list(cls, chart_list):
        session = get_session()
        try:
            chart_ids = [chart.id for chart in chart_list]
            if not chart_ids:
                return

            # 直接执行原生批量删除
            stmt = delete(ChartInfo).where(ChartInfo.id.in_(chart_ids))
            with session.begin():
                session.execute(stmt)
        except Exception as e:
            session.rollback()
            Log.error(f"原生SQL删除失败: {str(e)}")
            raise
        finally:
            session.close()


class AppSQL:

    @classmethod
    def list_apps(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 根据query_params查询数据
            query = session.query(AppInfo)

            # 数据库查询参数
            if "id" in query_params and query_params["id"]:
                query = query.filter(AppInfo.id == query_params["id"])
            if "cluster_id" in query_params and query_params["cluster_id"]:
                query = query.filter(AppInfo.cluster_id == query_params["cluster_id"])
            if "status" in query_params and query_params["status"]:
                query = query.filter(AppInfo.status == query_params["status"])
            if "repo_name" in query_params and query_params["repo_name"]:
                query = query.filter(AppInfo.repo_name == query_params["repo_name"])
            if "name" in query_params and query_params["name"]:
                query = query.filter(AppInfo.name == query_params["name"])
            if "cluster_id" in query_params and query_params["cluster_id"]:
                query = query.filter(AppInfo.cluster_id == query_params["cluster_id"])
            if "tag_id" in query_params and query_params["tag_id"]:
                query = query.filter(AppInfo.tag_id == query_params["tag_id"])
            if "tag_name" in query_params and query_params["tag_name"]:
                query = query.filter(AppInfo.tag_name == query_params["tag_name"])
            if "type" in query_params and query_params["type"]:
                query = query.filter(AppInfo.type == query_params["type"])
            if "chart_id" in query_params and query_params["chart_id"]:
                query = query.filter(AppInfo.chart_id == query_params["chart_id"])
            if "repo_id" in query_params and query_params["repo_id"]:
                query = query.filter(AppInfo.repo_id == query_params["repo_id"])
            if "namespace" in query_params and query_params["namespace"]:
                query = query.filter(AppInfo.namespace == query_params["namespace"])
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in app_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None :
                    query = query.order_by(app_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(app_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(AppInfo.create_time.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            app_list = query.all()
            # 返回
            return count, app_list

    @classmethod
    def create_app(cls, app):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(app)

    @classmethod
    def update_app(cls, app):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(app)

    @classmethod
    def delete_app_list(cls, app_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        try:
            app_ids = [app.id for app in app_list]
            if not app_ids:
                return

            # 直接执行原生批量删除
            stmt = delete(AppInfo).where(AppInfo.id.in_(app_ids))
            with session.begin():
                session.execute(stmt)
        except Exception as e:
            session.rollback()
            Log.error(f"原生SQL删除失败: {str(e)}")
            raise
        finally:
            session.close()

    @classmethod
    def delete_app(cls, app):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.delete(app)


class TagSQL:

    @classmethod
    def list_tags(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 根据query_params查询数据
            query = session.query(TagInfo)

            # 数据库查询参数
            if "id" in query_params and query_params["id"]:
                query = query.filter(TagInfo.id == query_params["id"])
            if "name" in query_params and query_params["name"]:
                query = query.filter(TagInfo.name == query_params["name"])
            if "chinese_name" in query_params and query_params["chinese_name"]:
                query = query.filter(TagInfo.chinese_name == query_params["chinese_name"])
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in tag_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None :
                    query = query.order_by(tag_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(tag_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(TagInfo.name.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            tag_list = query.all()
            # 返回
            return count, tag_list

    @classmethod
    def create_tag(cls, tag):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(tag)

    @classmethod
    def update_tag(cls, tag):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(tag)

    @classmethod
    def delete_tag_list(cls, tag_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        for tag in tag_list:
            cls.delete_tag(tag)

    @classmethod
    def delete_tag(cls, tag):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.delete(tag)

