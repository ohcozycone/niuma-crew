"""添加系统内置工作区；不变更已有连接和员工许可。"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = depends_on = None


def upgrade():
    for statement in INSERTS:
        op.execute(statement)


def downgrade():
    raise RuntimeError("内置工作区可能已有员工引用，不支持有损降级，请恢复升级前备份。")


# 固定发布时的目录，不让历史迁移依赖后续应用代码，也支持离线 SQL。
INSERTS = (
    'INSERT INTO tool_connections (id,name,kind,provider_key,auth_type,public_config,approved_catalog,enabled,config_revision,credential_revision,catalog_revision,account_scope,created_by_user_id) VALUES (\'3d1eb5bd-2722-48eb-991c-1583b56ab281\',\'文件读写与文本成果\',\'native\',\'workspace\',\'none\',\'{"workspace_mode":"virtual"}\',\'[{"name":"ls","description":"列出获准目录中的文件和子目录。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"12cf42b0f38268c1d0eff21b8e85b5cb02c3287d0e9d01e130701f53d32a67d1"},{"name":"read_file","description":"读取获准文件的内容，文本可按行分段读取。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"f3929083ea0789611cce1f777ef00f563fb46abf3ab5da9ddee399e54520ccc0"},{"name":"glob","description":"按文件名模式查找获准目录中的文件。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"3ff7f1b72a1fbee1aa01da6b66824c9d2148687d195ca08fde15d69925ccf61d"},{"name":"grep","description":"搜索获准文本文件中的内容。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"5a1c8a724a34b4e89638f6deceea3fc0d0eaa74d0f59fe8fecb67392808c8daf"},{"name":"write_file","description":"在获准目录创建或写入文本文件。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"5e9b0f18ca12846b8feeaf27ed4b4d64d48ab5db35667d93b7baaf220c1286c7"},{"name":"edit_file","description":"通过文本匹配编辑获准文件。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"606d735db15a8d7343e996b84bc3c970b72dcb429fb150f656a442ad0381fb8c"},{"name":"delete","description":"删除获准工作目录中的文件或目录，需要单独选择该操作。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"a842782654e315998437121cfc7063518da9d60df4f320108544a4b258b3f732"}]\',1,1,1,1,\'shared\',NULL)',
    'INSERT INTO tool_connections (id,name,kind,provider_key,auth_type,public_config,approved_catalog,enabled,config_revision,credential_revision,catalog_revision,account_scope,created_by_user_id) VALUES (\'3d1eb5bd-2722-48eb-991c-1583b56ab282\',\'代码执行\',\'native\',\'workspace\',\'none\',\'{"workspace_mode":"sandbox"}\',\'[{"name":"ls","description":"列出获准目录中的文件和子目录。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"1e1d511a140254f93a060bf36607ce13160f685507c207fba422e1aba789017d"},{"name":"read_file","description":"读取获准文件的内容，文本可按行分段读取。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"da6667e25976033d914cc1fda1145962694e2e8ca9c703f892bb1b46f55f8676"},{"name":"glob","description":"按文件名模式查找获准目录中的文件。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"edf52f650f691dbe466268e9463521bb82d5421e8983f62fcb0029cd4f0ac382"},{"name":"grep","description":"搜索获准文本文件中的内容。","input_schema":{"type":"object"},"recovery":"readonly","descriptor_hash":"5089afbcab3f41ed764b086c3e4942a41152f5b742f3fe73f28ce592a58bd27b"},{"name":"write_file","description":"在获准目录创建或写入文本文件。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"29445433b4d7f19ca286bfe057fce82ffb6b19f9656ee06f00c5ec7bd072671f"},{"name":"edit_file","description":"通过文本匹配编辑获准文件。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"088a6c3e9e488e1fe864f5edcb596c8f1250df941a2ff57c2e38c3209baa736a"},{"name":"delete","description":"删除获准工作目录中的文件或目录，需要单独选择该操作。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"befa914bddab9c779ce47e1d012c36649c4b64a91b13772c32e7a0ccda04e057"},{"name":"execute","description":"在本轮独占沙箱中执行 Shell 命令，运行镜像中已安装的程序。","input_schema":{"type":"object"},"recovery":"never","descriptor_hash":"a17d872af37c328dd16fa33bea0333446e87bfc1aff467b75f0369a51b4dc46b"}]\',1,1,1,1,\'shared\',NULL)',
)
