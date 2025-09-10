
      function dropdown() {
        return {
          options: [],
          selected: [],
          show: false,

          open() {
            this.show = !this.show;
          },
          close() {
            this.show = false;
          },
          isOpen() {
            return this.show;
          },

          select(index, event) {
            const option = this.options[index];
            if (!option.selected) {
              option.selected = true;
              this.selected.push(index);
            } else {
              option.selected = false;
              this.selected = this.selected.filter((i) => i !== index);
            }
          },

          remove(index, optionIndex) {
            this.options[optionIndex].selected = false;
            this.selected.splice(index, 1);
          },

          loadOptions() {
            const options = document.getElementById("select").options;
            for (let i = 0; i < options.length; i++) {
              this.options.push({
                value: options[i].value,
                text: options[i].innerText,
                selected: options[i].hasAttribute("selected"),
              });
            }
          },

          selectedValues() {
            return this.selected.map((i) => this.options[i].value).join(",");
          },
        };
      }
    

