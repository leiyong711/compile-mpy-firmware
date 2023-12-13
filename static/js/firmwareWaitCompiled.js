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
        isDialogVisible: false, // �Ƿ���ʾ���������
        passwordInput: '',    // ����������ֵ
        downloadType: 0,    // ��������
        firmwareId: null,   // Ҫ���صĹ̼���ID

        total: 0,
        pageSize: 5,
        currentPage: 1,

    },
    mounted() {
        this.onSubmit();  // ҳ�����ʱ��������
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
                    return '����ɹ�';
                case 1:
                    return '����ʧ��';
                case 2:
                    return '������';
                case 3:
                    return '�ȴ�����';
                default:
                    return 'δ֪״̬';
            }
        },
        // ÿҳ��ʾ�����ı�ʱ����
        handleSizeChange(val) {
            console.log(`ÿҳ ${val} ��`);
            this.pageSize = val;
            this.onSubmit();  // ��ÿҳ�ļ�¼���ı�ʱ�����·�������
        },
        // ��ǰҳ�ı�ʱ����
        handleCurrentChange(val) {
            console.log(`��ǰҳ: ${val}`);
            this.currentPage = val;
            this.onSubmit();  // ��ǰҳ��ı�ʱ�����·�������
        },
        // ����Դ�ļ�
        handleDownloadSourceFile(index, row) {
            console.log(index, row);
            this.firmwareId = row.id;
            this.downloadType = 0;
            this.passwordInput = '';

            if (row.retrieve_password){
                this.isDialogVisible = true;
            }else{
                this.isDialogVisible = false;
                this.download()  // ����
            }
        },
        // ����bin�ļ�
        handleDownloadBin(index, row) {
            console.log(index, row);
            this.firmwareId = row.id;
            this.downloadType = 1;
            this.passwordInput = '';

            if (row.retrieve_password){
                this.isDialogVisible = true;
            }else{
                this.isDialogVisible = false;
                this.download()  // ����
            }
        },
        // ȷ������
        handlePasswordConfirm() {
            this.isDialogVisible = false;
            this.download(this.passwordInput)   // ����
        },
        // ����
        download(retrieve_password=null){
            let params = {
                firmware_id: this.firmwareId,  // �̼�ID
                file_type: this.downloadType,  // �ļ�����
            };
            if (retrieve_password) {
                params.retrieve_password = retrieve_password;
            };

            axios({
                url: '/api/download',
                method: 'GET',
                responseType: 'arraybuffer',  // ������Ӧ����Ϊblob
                params: params
            })
                .then(response => {
                    // ���Խ���Ӧ����ΪJSON
                    try {
                        const json = JSON.parse(new TextDecoder("utf-8").decode(new Uint8Array(response.data)));
                        if (json.code && json.message) {
                            // ������Ϣ
                            this.$message.error(`Error: ${json.message}`);
                        }
                    } catch(e) {
                        // �������ʧ�ܣ�����Ӧ״̬���ʾ�ɹ�����ô�ʹ����ļ�����
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
                                    link.setAttribute('download', fileName);  // ʹ�ô���Ӧͷ�л�ȡ���ļ���
                                    document.body.appendChild(link);
                                    link.click();
                                } else {
                                    // ������Ϣ
                                    // this.$message.error(`Error: �޷������ļ���`);
                                }
                            } else {
                                // ������Ϣ
                                // this.$message.error(`Error: �޷������ļ���`);
                            }
                        }
                    }
                })
                .catch(error => {
                    this.$message({
                        message: `�����ļ�����: ${error}`,
                        type: 'error'
                    });
                });
        },
        // ��ѯ
        onSubmit() {
            console.log('submit!', this.formInline);
            let params = {
                page: this.currentPage,
                limit: this.pageSize,
                id: null, // ������Ը�������������
                email: this.formInline.email,
                flash_size: this.formInline.flash_size,
                device_type: this.formInline.device_type,
                sort: this.formInline.sort,
            };
            axios.get('/api/get_firmware_wait_compiled_list', {params: params})
                .then(response => {
                    console.log(response.data);
                    this.tableData = response.data.data.items;  // ����tableData
                    this.total = response.data.data.total;  // �����ܼ�¼��
                })
                .catch(error => {
                    // console.error(error);
                    this.$message({
                        message: `��ȡ�б����: ${error}`,
                        type: 'error'
                    });
                });
        },
    }
});