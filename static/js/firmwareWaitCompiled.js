new Vue({
    el: '#app',
    data: {
        formInline: {
            email: '',
            device_type: 'all',
            flash_size: 'all',
            sort: '-id',
        },
        tableData: [],
        isDialogVisible: false, // 是否显示密码输入框
        passwordInput: '',    // 密码输入框的值
        downloadType: 0,    // 下载类型
        firmwareId: null,   // 要下载的固件的ID

        total: 0,
        pageSize: 5,
        currentPage: 1,

    },
    mounted() {
        this.onSubmit();  // 页面加载时发送请求
    },
    methods: {
        getTagType(status) {
            switch (status) {
                case 0:
                    return 'success';
                case 1:
                    return 'danger';
                case 2:
                    return 'warning';
                case 3:
                    return 'info';
                default:
                    return 'info';
            }
        },
        getTagText(status) {
            switch (status) {
                case 0:
                    return '编译成功';
                case 1:
                    return '编译失败';
                case 2:
                    return '编译中';
                case 3:
                    return '等待编译';
                default:
                    return '未知状态';
            }
        },
        // 每页显示条数改变时触发
        handleSizeChange(val) {
            console.log(`每页 ${val} 条`);
            this.pageSize = val;
            this.onSubmit();  // 当每页的记录数改变时，重新发送请求
        },
        // 当前页改变时触发
        handleCurrentChange(val) {
            console.log(`当前页: ${val}`);
            this.currentPage = val;
            this.onSubmit();  // 当前页码改变时，重新发送请求
        },
        // 下载源文件
        handleDownloadSourceFile(index, row) {
            console.log(index, row);
            this.firmwareId = row.id;
            this.downloadType = 0;
            this.passwordInput = '';

            if (row.retrieve_password){
                this.isDialogVisible = true;
            }else{
                this.isDialogVisible = false;
                this.download()  // 下载
            }
        },
        // 下载bin文件
        handleDownloadBin(index, row) {
            console.log(index, row);
            this.firmwareId = row.id;
            this.downloadType = 1;
            this.passwordInput = '';

            if (row.retrieve_password){
                this.isDialogVisible = true;
            }else{
                this.isDialogVisible = false;
                this.download()  // 下载
            }
        },
        // 确认密码
        handlePasswordConfirm() {
            this.isDialogVisible = false;
            this.download(this.passwordInput)   // 下载
        },
        // 下载
        download(retrieve_password=null){
            let params = {
                firmware_id: this.firmwareId,  // 固件ID
                file_type: this.downloadType,  // 文件类型
            };
            if (retrieve_password) {
                params.retrieve_password = retrieve_password;
            };

            axios({
                url: '/api/download',
                method: 'GET',
                responseType: 'arraybuffer',  // 设置响应类型为blob
                params: params
            })
                .then(response => {
                    // 尝试将响应解析为JSON
                    try {
                        const json = JSON.parse(new TextDecoder("utf-8").decode(new Uint8Array(response.data)));
                        if (json.code && json.message) {
                            // 错误消息
                            this.$message.error(`Error: ${json.message}`);
                        }
                    } catch(e) {
                        // 如果解析失败，但响应状态码表示成功，那么就处理文件下载
                        if (response.status >= 200 && response.status < 300) {
                            const contentDisposition = response.headers['content-disposition'];
                            if (contentDisposition) {
                                const fileNameMatch = contentDisposition.match(/filename="(.+)"/);
                                if (fileNameMatch && fileNameMatch.length === 2) {
                                    const fileName = fileNameMatch[1];
                                    const blob = new Blob([response.data]);
                                    const url = window.URL.createObjectURL(blob);
                                    const link = document.createElement('a');
                                    link.href = url;
                                    link.setAttribute('download', fileName);  // 使用从响应头中获取的文件名
                                    document.body.appendChild(link);
                                    link.click();
                                } else {
                                    // 错误消息
                                    // this.$message.error(`Error: 无法检索文件名`);
                                }
                            } else {
                                // 错误消息
                                // this.$message.error(`Error: 无法检索文件名`);
                            }
                        }
                    }
                })
                .catch(error => {
                    this.$message({
                        message: `下载文件错误: ${error}`,
                        type: 'error'
                    });
                });
        },
        // 查询
        onSubmit() {
            console.log('submit!', this.formInline);
            let params = {
                page: this.currentPage,
                limit: this.pageSize,
                id: null, // 这里可以根据你的需求更改
                email: this.formInline.email,
                flash_size: this.formInline.flash_size,
                device_type: this.formInline.device_type,
                sort: this.formInline.sort,
            };
            axios.get('/api/get_firmware_wait_compiled_list', {params: params})
                .then(response => {
                    console.log(response.data);
                    this.tableData = response.data.data.items;  // 更新tableData
                    this.total = response.data.data.total;  // 更新总记录数
                })
                .catch(error => {
                    // console.error(error);
                    this.$message({
                        message: `获取列表错误: ${error}`,
                        type: 'error'
                    });
                });
        },
    }
});