class DataMenu extends HTMLElement {
    constructor() {
        super();

        const shadow = this.attachShadow({mode: 'open'});
        
        const template = document.createElement("template");
        template.innerHTML = `
            <style>
                #container {
                    height: 100vh;
                    width: 200px;
                    border-right: 5px solid rgb(45, 45, 45);

                    display: flex;
                    flex-direction: column;

                    margin: 0;
                    padding: 0;
                }

                .menu-item {
                    padding: 15px;
                    font-size: 20px;
                
                    cursor: pointer;
                }
                
                .menu-item:not(:first-of-type) {
                    border-top: 3px dashed rgb(45, 45, 45);
                }
                
                .menu-item:last-of-type {
                    border-bottom: 3px solid rgb(45, 45, 45);
                }
                
                .menu-item:hover {
                    background-color: rgb(45, 45, 45);
                }
            </style>
            <div id="container"></div>
        `;
        var clone = template.content.cloneNode(true);
        var container = clone.getElementById("container");

        const data_path = this.getAttribute('data');
        fetch(data_path)
            .then(response => response.json())
            .then(data => {
                for (const item of data){
                    const menu_item = document.createElement('div');
                    menu_item.setAttribute('class', 'menu-item');
                    menu_item.textContent = item.name;
                    menu_item.addEventListener(
                        "click",
                        _ => window.location.href = item.url
                    );

                    container.appendChild(menu_item);                    
                }
                shadow.appendChild(clone);
            });
    }
}

customElements.define('data-menu', DataMenu);